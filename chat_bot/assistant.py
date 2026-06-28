"""
Assistant class for summarizing chat messages using LangChain and AI.
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional, TypedDict, Union

from dotenv import load_dotenv
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

# LangChain imports
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

# Import MessageFormatter
from .formatter import MessageFormatter
from .logging_config import get_logger, sanitize_for_logging
from .metrics import record_ai_request
from .models import (
    AIConfig,
    Message,
    MessagesData,
    SummaryResponse,
    TaskExtractionResponse,
    UserProfile,
)
from .models.summary_response import SummaryOutput
from .models.task_extraction_response import TaskExtractionOutput
from .scenario_loader import load_relevant_scenarios
from .tool_router import ToolRouter

# Load environment variables
load_dotenv()

# Configure logging
logger = get_logger(__name__)


class AgentGraphState(TypedDict, total=False):
    """State for the LangGraph-based tool execution flow."""

    messages: Annotated[List[BaseMessage], add_messages]
    route: str
    requires_tool: bool
    route_confidence: float
    worker: str
    user_goal: str
    entity_type: str
    entity_name: str
    time_period: str
    missing_fields: List[str]
    task_brief: str
    selected_tool_names: List[str]
    tool_validation_failed: bool
    final_response: str


class Assistant:
    """
    Assistant class that uses LangChain with AI to summarize chat messages.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        project: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        """
        Initialize the Assistant with AI configuration.

        Args:
            api_key: AI API key (defaults to AI_API_KEY env var)
            model: AI model name (defaults to AI_MODEL env var)
            base_url: AI base URL (defaults to AI_BASE_URL env var)
            project: Provider-specific project/folder (defaults to AI_PROJECT env var)
            temperature: Temperature for generation (
                defaults to AI_TEMPERATURE env var
            )
            max_tokens: Max tokens for generation (
                defaults to AI_MAX_TOKENS env var
            )
        """
        # Get configuration from environment or parameters
        api_key = api_key or os.getenv("AI_API_KEY")
        model = model or os.getenv("AI_MODEL", "")
        base_url = base_url or os.getenv("AI_BASE_URL")
        project = project or os.getenv("AI_PROJECT")
        temperature = temperature or float(os.getenv("AI_TEMPERATURE", "0.3"))
        max_tokens = max_tokens or int(os.getenv("AI_MAX_TOKENS", "500"))
        light_model = os.getenv("AI_LIGHT_MODEL")
        light_base_url = os.getenv("AI_LIGHT_BASE_URL")
        light_api_key = os.getenv("AI_LIGHT_API_KEY")
        light_temperature = float(os.getenv("AI_LIGHT_TEMPERATURE", "0.0"))
        light_max_tokens = int(os.getenv("AI_LIGHT_MAX_TOKENS", str(max_tokens)))

        # Validate configuration using Pydantic model
        if not api_key:
            raise ValueError("API key is required")
        if not model:
            raise ValueError("Model name is required")

        self.config = AIConfig(
            api_key=api_key,
            model=model,
            base_url=base_url,
            project=project,
            temperature=temperature,
            max_tokens=max_tokens,
            light_api_key=light_api_key,
            light_model=light_model,
            light_base_url=light_base_url,
            light_temperature=light_temperature,
            light_max_tokens=light_max_tokens,
        )

        # Initialize the AI chat model
        self._init_llm()
        self._init_light_llm()
        self.routing_llm = self.light_llm or self.llm
        self.summary_llm = self.light_llm or self.llm
        self.direct_answer_llm = self.light_llm or self.llm
        self.tool_router = ToolRouter(self.routing_llm)

        # Load the prompt templates
        self._load_prompts()

    def _load_prompts(self) -> None:
        """Load prompt templates from files."""
        try:
            prompts_dir = Path(__file__).parent / "prompts"
            summary_prompt_file = prompts_dir / "summary.txt"
            task_extraction_prompt_file = prompts_dir / "task_extraction.txt"

            # Load chat_with_tools prompt
            chat_with_tools_prompt_file = prompts_dir / "chat_with_tools.txt"
            if chat_with_tools_prompt_file.exists():
                with open(chat_with_tools_prompt_file, "r", encoding="utf-8") as f:
                    self.chat_with_tools_prompt_template = f.read()
                logger.info("Loaded chat_with_tools prompt from file")
            else:
                logger.warning(
                    f"Chat with tools prompt file not found: {chat_with_tools_prompt_file}"
                )
                self.chat_with_tools_prompt_template = (
                    "Ты — AI-ассистент для управления задачами в системе Kaiten. "
                    "Отвечай только на русском языке. "
                    "Если инструмент вернул ошибку, обязательно сообщи об этом пользователю. "
                    "Текущая дата и время: {current_datetime}"
                )

            # Load summary prompt
            if summary_prompt_file.exists():
                with open(summary_prompt_file, "r", encoding="utf-8") as f:
                    summary_template = f.read()

                self.summary_prompt = ChatPromptTemplate.from_template(summary_template)
                logger.info("Loaded summary prompt from file")
            else:
                logger.warning(f"Summary prompt file not found: {summary_prompt_file}")
                # Fallback to default prompt
                self.summary_prompt = ChatPromptTemplate.from_template(
                    "You are an assistant for creating brief chat summaries. "
                    "Please provide your response in Russian.\n\n{messages}\n\n"
                    "Create a brief summary in Russian."
                )

            # Load task extraction prompt
            if task_extraction_prompt_file.exists():
                with open(task_extraction_prompt_file, "r", encoding="utf-8") as f:
                    task_extraction_template = f.read()

                self.task_extraction_prompt = ChatPromptTemplate.from_template(
                    task_extraction_template
                )
                logger.info("Loaded task extraction prompt from file")
            else:
                logger.warning(
                    f"Task extraction prompt file not found: {task_extraction_prompt_file}"
                )
                # Fallback to default prompt
                self.task_extraction_prompt = ChatPromptTemplate.from_template(
                    "You are an assistant for extracting tasks from chat messages. "
                    "Please provide your response in JSON format with tasks array.\n\n"
                    "{messages}\n\nExtract tasks in JSON format."
                )

        except Exception as e:
            logger.error(f"Failed to load prompts: {e}")
            # Fallback to default prompts
            self.chat_with_tools_prompt_template = (
                "Ты — AI-ассистент для управления задачами в системе Kaiten. "
                "Отвечай только на русском языке. "
                "Если инструмент вернул ошибку, обязательно сообщи об этом пользователю. "
                "Текущая дата и время: {current_datetime}"
            )
            self.summary_prompt = ChatPromptTemplate.from_template(
                "You are an assistant for creating brief chat summaries. "
                "Please provide your response in Russian.\n\n{messages}\n\n"
                "Create a brief summary in Russian."
            )
            self.task_extraction_prompt = ChatPromptTemplate.from_template(
                "You are an assistant for extracting tasks from chat messages. "
                "Please provide your response in JSON format with tasks array.\n\n"
                "{messages}\n\nExtract tasks in JSON format."
            )

    def _init_llm(self) -> None:
        """Initialize the language model."""
        try:
            llm_kwargs: Dict[str, Any] = {
                "api_key": SecretStr(self.config.api_key),
                "model": self.config.model,
                "temperature": self.config.temperature,
                "base_url": self.config.base_url,
                "max_completion_tokens": self.config.max_tokens,
            }

            if self.config.project:
                llm_kwargs["default_headers"] = {
                    "OpenAI-Project": self.config.project,
                }

            # Initialize with required parameters
            self.llm = ChatOpenAI(**llm_kwargs)
            logger.info(
                f"Initialized AI model: {self.config.model} "
                f"(temp: {self.config.temperature}, max_tokens: {self.config.max_tokens})"
            )

        except Exception as e:
            logger.error(f"Failed to initialize AI model: {e}")
            raise

    def _init_light_llm(self) -> None:
        """Initialize optional lightweight model for routing and cheap tasks."""
        self.light_llm = None
        if not self.config.light_model:
            logger.info("Light AI model is not configured; using main model")
            return

        try:
            light_api_key = self.config.light_api_key or "ollama"
            light_base_url = self.config.light_base_url or "http://localhost:11434/v1"
            llm_kwargs: Dict[str, Any] = {
                "api_key": SecretStr(light_api_key),
                "model": self.config.light_model,
                "temperature": self.config.light_temperature,
                "base_url": light_base_url,
                "max_completion_tokens": self.config.light_max_tokens,
            }
            self.light_llm = ChatOpenAI(**llm_kwargs)
            logger.info(
                "Initialized light AI model: %s (base_url: %s, temp: %s, max_tokens: %s)",
                self.config.light_model,
                light_base_url,
                self.config.light_temperature,
                self.config.light_max_tokens,
            )
        except Exception as e:
            logger.error(f"Failed to initialize light AI model: {e}")
            raise

    async def summarize(
        self, messages_input: Union[str, Dict[str, Any], MessagesData]
    ) -> SummaryResponse:
        """
        Summarize messages from either a JSON string, dictionary, or MessagesData object.

        Args:
            messages_input: Either a JSON string, dictionary, or MessagesData object
            containing messages data

        Returns:
            SummaryResponse object with the summary and metadata
        """
        start_time = time.time()

        try:
            # Handle different input types
            if isinstance(messages_input, str):
                # Parse JSON string
                data = json.loads(messages_input)
                messages_data = MessagesData(**data)
            elif isinstance(messages_input, dict):
                # Use dictionary directly
                messages_data = MessagesData(**messages_input)
            elif isinstance(messages_input, MessagesData):
                # Use MessagesData object directly
                messages_data = messages_input
            else:
                raise ValueError(
                    "Input must be either a JSON string, dictionary, or MessagesData object"
                )

            # Format messages for summarization
            formatted_messages = MessageFormatter.format_messages_for_summary(
                messages_data
            )

            # Create the prompt
            prompt = self.summary_prompt.format(messages=formatted_messages)

            # Create model with structured output
            model_with_structure = self.summary_llm.with_structured_output(
                SummaryOutput
            )

            # Generate summary response using structured output
            ai_started_at = time.perf_counter()
            try:
                structured_output: SummaryOutput = await model_with_structure.ainvoke(prompt)  # type: ignore
                record_ai_request(
                    operation="summary",
                    model=self._llm_model_name(self.summary_llm),
                    status="success",
                    started_at=ai_started_at,
                    response=structured_output,
                )
            except Exception:
                record_ai_request(
                    operation="summary",
                    model=self._llm_model_name(self.summary_llm),
                    status="error",
                    started_at=ai_started_at,
                )
                raise

            processing_time = time.time() - start_time
            logger.info("Successfully generated summary")

            return SummaryResponse(
                summary=structured_output.summary,
                success=True,
                error_message=None,
                processing_time=processing_time,
            )

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            return SummaryResponse(
                summary="",
                success=False,
                error_message=f"Ошибка: Неверный формат JSON данных. {str(e)}",
                processing_time=time.time() - start_time,
            )

        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
            return SummaryResponse(
                summary="",
                success=False,
                error_message=f"Ошибка при создании сводки: {str(e)}",
                processing_time=time.time() - start_time,
            )

    async def extract_tasks(
        self, messages_input: Union[str, Dict[str, Any], MessagesData]
    ) -> TaskExtractionResponse:
        """
        Extract tasks from messages using LangChain's structured output.

        Args:
            messages_input: Either a JSON string, dictionary, or MessagesData object
            containing messages data

        Returns:
            TaskExtractionResponse object with extracted tasks and metadata
        """
        start_time = time.time()

        try:
            # Handle different input types
            if isinstance(messages_input, str):
                # Parse JSON string
                data = json.loads(messages_input)
                messages_data = MessagesData(**data)
            elif isinstance(messages_input, dict):
                # Use dictionary directly
                messages_data = MessagesData(**messages_input)
            elif isinstance(messages_input, MessagesData):
                # Use MessagesData object directly
                messages_data = messages_input
            else:
                raise ValueError(
                    "Input must be either a JSON string, dictionary, or MessagesData object"
                )

            # Format messages for task extraction
            formatted_messages = MessageFormatter.format_messages_for_summary(
                messages_data
            )

            # Get current date for context
            current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Create the prompt
            prompt = self.task_extraction_prompt.format(
                messages=formatted_messages, current_date=current_date
            )

            # Create model with structured output
            model_with_structure = self.llm.with_structured_output(TaskExtractionOutput)

            # Generate task extraction response using structured output
            ai_started_at = time.perf_counter()
            try:
                structured_output: TaskExtractionOutput = await model_with_structure.ainvoke(prompt)  # type: ignore
                record_ai_request(
                    operation="task_extraction",
                    model=self.config.model,
                    status="success",
                    started_at=ai_started_at,
                    response=structured_output,
                )
            except Exception:
                record_ai_request(
                    operation="task_extraction",
                    model=self.config.model,
                    status="error",
                    started_at=ai_started_at,
                )
                raise

            processing_time = time.time() - start_time
            logger.info(f"Successfully extracted {len(structured_output.tasks)} tasks")

            return TaskExtractionResponse(
                tasks=structured_output.tasks,
                success=True,
                error_message=None,
                processing_time=processing_time,
            )

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            return TaskExtractionResponse(
                tasks=[],
                success=False,
                error_message=f"Ошибка: Неверный формат JSON данных. {str(e)}",
                processing_time=time.time() - start_time,
            )

        except Exception as e:
            logger.error(f"Failed to extract tasks: {e}")
            return TaskExtractionResponse(
                tasks=[],
                success=False,
                error_message=f"Ошибка при извлечении задач: {str(e)}",
                processing_time=time.time() - start_time,
            )

    def _convert_history_to_langchain_messages(
        self, history: List[Message]
    ) -> List[BaseMessage]:
        """Convert chat history to LangChain message format.

        Args:
            history: List of Message objects from conversation history.

        Returns:
            List of LangChain BaseMessage objects.
        """
        langchain_messages: List[BaseMessage] = []

        for msg in history:
            if not msg.text:
                continue

            if msg.is_bot_message:
                langchain_messages.append(AIMessage(content=msg.text))
            else:
                langchain_messages.append(HumanMessage(content=msg.text))

        return langchain_messages

    @staticmethod
    def _select_history_for_agent(history: List[Message]) -> List[Message]:
        """Keep user context while excluding stale bot replies from the agent state.

        Old assistant answers can anchor the model to outdated assumptions.
        Preserve all user turns and only keep bot turns that are directly
        referenced via replies or are the latest bot context item.
        """
        if not history:
            return []

        referenced_bot_ids = {
            msg.reply_to_message_id
            for msg in history
            if not msg.is_bot_message and msg.reply_to_message_id is not None
        }

        latest_bot_message_id = next(
            (msg.message_id for msg in reversed(history) if msg.is_bot_message),
            None,
        )

        selected: List[Message] = []
        for msg in history:
            if not msg.is_bot_message:
                selected.append(msg)
                continue
            if (
                msg.message_id in referenced_bot_ids
                or msg.message_id == latest_bot_message_id
            ):
                selected.append(msg)

        return selected

    def _log_agent_trace(self, messages: List[BaseMessage]) -> None:
        """Log the final agent execution trace step-by-step."""
        for index, msg in enumerate(messages):
            if isinstance(msg, HumanMessage):
                logger.info(
                    "Agent step",
                    extra={
                        "event_type": "agent_step",
                        "step_index": index,
                        "step_kind": "human_message",
                        "content": sanitize_for_logging(
                            getattr(msg, "content", ""), max_length=1000
                        ),
                    },
                )
                continue

            if isinstance(msg, ToolMessage):
                logger.info(
                    "Agent step",
                    extra={
                        "event_type": "agent_step",
                        "step_index": index,
                        "step_kind": "tool_result",
                        "tool_name": getattr(msg, "name", None),
                        "tool_call_id": getattr(msg, "tool_call_id", None),
                        "content": sanitize_for_logging(
                            getattr(msg, "content", ""), max_length=2000
                        ),
                    },
                )
                continue

            if isinstance(msg, AIMessage):
                tool_calls = getattr(msg, "tool_calls", []) or []
                logger.info(
                    "Agent step",
                    extra={
                        "event_type": "agent_step",
                        "step_index": index,
                        "step_kind": "ai_message",
                        "content": sanitize_for_logging(
                            getattr(msg, "content", ""), max_length=1000
                        ),
                        "tool_calls": sanitize_for_logging(tool_calls, max_length=1000),
                    },
                )

    async def chat_with_tools(
        self,
        message: str,
        tools: Optional[List[Any]] = None,
        history: Optional[List[Message]] = None,
        user_profile: Optional[UserProfile] = None,
    ) -> str:
        """Chat with AI using LangGraph ReAct agent for multi-step tool calling.

        Uses LangGraph's prebuilt ReAct agent to enable sequential tool execution.
        The agent can call multiple tools in sequence, using results from one tool
        to inform the next, until the task is complete or max iterations reached.

        Args:
            message: User message to process.
            tools: List of LangChain tools to use (optional).
            history: Conversation history as list of Message objects (optional).
            user_profile: Persistent user profile for self-reference resolution.

        Returns:
            str: AI response after processing tool calls.
        """
        start_time = time.time()

        try:
            if not tools:
                logger.warning("No tools provided for chat_with_tools")
                return "❌ Инструменты не настроены"

            # Build system prompt with current datetime
            current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            system_prompt = self.chat_with_tools_prompt_template.format(
                current_datetime=current_datetime
            )
            scenarios_content = load_relevant_scenarios(message=message)
            if scenarios_content:
                system_prompt += scenarios_content
            if user_profile is not None:
                profile_context = (
                    "\n\n## Контекст пользователя\n"
                    f"- Telegram display name: {user_profile.telegram_display_name}\n"
                    f"- Представился как: {user_profile.introduced_name}\n"
                )
                if user_profile.kaiten_user_name:
                    profile_context += (
                        f"- Имя в Kaiten: {user_profile.kaiten_user_name}\n"
                        "- Если пользователь пишет 'на меня', 'мне', 'меня', "
                        "'назначь мне' или аналогично про самого себя, "
                        f"используй имя в Kaiten: {user_profile.kaiten_user_name}.\n"
                    )
                else:
                    profile_context += (
                        "- Имя в Kaiten не заполнено. Если пользователь просит "
                        "назначить задачу на себя, сначала попроси его обновить "
                        "профиль через /introduce и указать kaiten.\n"
                    )
                system_prompt += profile_context
            logger.info(
                "Starting LangGraph agent run",
                extra={
                    "event_type": "agent_run_started",
                    "tool_count": len(tools),
                    "tool_names": [getattr(tool, "name", str(tool)) for tool in tools],
                    "history_message_count": len(history) if history else 0,
                    "has_user_profile": user_profile is not None,
                },
            )

            # Build input messages with history if provided
            input_messages: List[BaseMessage] = []

            if history:
                history_limit = int(os.getenv("AGENT_HISTORY_MESSAGE_LIMIT", "12"))
                if history_limit > 0 and len(history) > history_limit:
                    history = history[-history_limit:]
                    logger.info(
                        "Trimmed conversation history to %d messages before agent run",
                        history_limit,
                    )
                filtered_history = self._select_history_for_agent(history)
                history_messages = self._convert_history_to_langchain_messages(
                    filtered_history
                )
                input_messages.extend(history_messages)
                logger.info(
                    "Added %d messages from conversation history",
                    len(history_messages),
                )

            # Add current user message
            input_messages.append(HumanMessage(content=message))

            graph = self._build_chat_graph(tools=tools, system_prompt=system_prompt)
            recursion_limit = int(os.getenv("AGENT_RECURSION_LIMIT", "25"))
            result = await graph.ainvoke(
                {
                    "messages": input_messages,
                    "route": "",
                    "requires_tool": False,
                    "route_confidence": 0.0,
                    "worker": "",
                    "user_goal": "",
                    "entity_type": "",
                    "entity_name": "",
                    "time_period": "",
                    "missing_fields": [],
                    "task_brief": "",
                    "selected_tool_names": [],
                    "tool_validation_failed": False,
                    "final_response": "",
                },
                config={"recursion_limit": recursion_limit},
            )

            # Extract final response from messages
            result_messages: List[BaseMessage] = result.get("messages", [])
            self._log_agent_trace(result_messages)
            final_content = result.get(
                "final_response", ""
            ) or self._extract_final_content(result_messages)

            processing_time = time.time() - start_time
            logger.info(
                "Chat with tools completed",
                extra={
                    "event_type": "agent_run_completed",
                    "duration_ms": round(processing_time * 1000, 2),
                    "result_message_count": len(result_messages),
                    "final_content": sanitize_for_logging(
                        final_content, max_length=1000
                    ),
                },
            )

            return final_content if final_content else "✅ Операция выполнена"

        except Exception as e:
            logger.error(f"Failed to process chat with tools: {e}", exc_info=True)
            return f"❌ Ошибка при обработке запроса: {str(e)}"

    def _build_chat_graph(self, tools: List[Any], system_prompt: str) -> Any:
        """Build a LangGraph workflow for routed tool execution."""
        tool_node = ToolNode(tools=tools, handle_tool_errors=True)
        graph = StateGraph(AgentGraphState)

        async def route_request(state: AgentGraphState) -> AgentGraphState:
            message_text = self._extract_last_human_message(state["messages"])
            history_text = self._format_messages_for_orchestrator(
                state["messages"][:-1]
            )
            decision = await self.tool_router.orchestrate(
                message=message_text,
                history=history_text,
                tools=tools,
            )
            selected_tools = self.tool_router.select_tools(
                route=decision.route,
                tools=tools,
            )
            final_response = ""
            if decision.needs_clarification and decision.clarification_question:
                final_response = decision.clarification_question
            requires_tool = (
                decision.route != "general_assistant"
                and not decision.needs_clarification
                and len(selected_tools) > 0
            )
            logger.info(
                "Assistant accepted orchestrator plan",
                extra={
                    "event_type": "assistant_orchestrator_plan",
                    "route": decision.route,
                    "worker": decision.worker,
                    "requires_tool": requires_tool,
                    "needs_clarification": decision.needs_clarification,
                    "user_goal": decision.user_goal,
                    "entity_type": decision.entity_type,
                    "entity_name": decision.entity_name,
                    "time_period": decision.time_period,
                    "missing_fields": decision.missing_fields,
                    "task_brief": sanitize_for_logging(
                        decision.task_brief, max_length=500
                    ),
                    "history_excerpt": sanitize_for_logging(
                        history_text, max_length=1000
                    ),
                    "message_text": sanitize_for_logging(message_text, max_length=300),
                },
            )

            return {
                "route": decision.route,
                "requires_tool": requires_tool,
                "route_confidence": decision.confidence,
                "worker": decision.worker,
                "user_goal": decision.user_goal,
                "entity_type": decision.entity_type or "",
                "entity_name": decision.entity_name or "",
                "time_period": decision.time_period or "",
                "missing_fields": decision.missing_fields,
                "task_brief": decision.task_brief,
                "selected_tool_names": [
                    getattr(tool, "name", str(tool)) for tool in selected_tools
                ],
                "tool_validation_failed": False,
                "final_response": final_response,
            }

        async def direct_answer(state: AgentGraphState) -> AgentGraphState:
            direct_llm = getattr(self, "direct_answer_llm", self.llm)
            ai_started_at = time.perf_counter()
            try:
                response = await direct_llm.ainvoke(
                    [
                        SystemMessage(
                            content=self._build_system_prompt(system_prompt, state)
                        )
                    ]
                    + state["messages"]
                )
                record_ai_request(
                    operation="chat_direct_answer",
                    model=self._llm_model_name(direct_llm),
                    status="success",
                    started_at=ai_started_at,
                    response=response,
                )
            except Exception:
                record_ai_request(
                    operation="chat_direct_answer",
                    model=self._llm_model_name(direct_llm),
                    status="error",
                    started_at=ai_started_at,
                )
                raise
            content = getattr(response, "content", "")
            return {
                "messages": [response],
                "final_response": content if isinstance(content, str) else "",
            }

        async def agent_step(state: AgentGraphState) -> AgentGraphState:
            selected_tools = self._filter_tools_by_names(
                tools=tools,
                tool_names=state.get("selected_tool_names", []),
            )
            model = self.llm.bind_tools(selected_tools)
            ai_started_at = time.perf_counter()
            try:
                response = await model.ainvoke(
                    [
                        SystemMessage(
                            content=self._build_system_prompt(system_prompt, state)
                        )
                    ]
                    + state["messages"]
                )
                record_ai_request(
                    operation="chat_agent_step",
                    model=getattr(getattr(self, "config", None), "model", None),
                    status="success",
                    started_at=ai_started_at,
                    response=response,
                )
            except Exception:
                record_ai_request(
                    operation="chat_agent_step",
                    model=getattr(getattr(self, "config", None), "model", None),
                    status="error",
                    started_at=ai_started_at,
                )
                raise
            return {
                "messages": [response],
                "tool_validation_failed": False,
            }

        def validate_tool_call(state: AgentGraphState) -> AgentGraphState:
            last_message = state["messages"][-1]
            if not isinstance(last_message, AIMessage):
                return {"tool_validation_failed": False}

            allowed_names = set(state.get("selected_tool_names", []))
            invalid_messages: List[ToolMessage] = []
            for tool_call in getattr(last_message, "tool_calls", []) or []:
                tool_name = tool_call.get("name", "")
                if tool_name not in allowed_names:
                    invalid_messages.append(
                        ToolMessage(
                            content=(
                                f"Инструмент {tool_name} недоступен для маршрута "
                                f"{state.get('route', 'unknown')}. Выбери другой "
                                "разрешённый инструмент или ответь без вызова."
                            ),
                            tool_call_id=tool_call.get("id", ""),
                            name=tool_name,
                        )
                    )

            if invalid_messages:
                return {
                    "messages": invalid_messages,
                    "tool_validation_failed": True,
                }
            return {"tool_validation_failed": False}

        def finalize(state: AgentGraphState) -> AgentGraphState:
            final_content = state.get(
                "final_response", ""
            ) or self._extract_final_content(state["messages"])
            return {"final_response": final_content}

        def route_after_router(state: AgentGraphState) -> str:
            if state.get("final_response"):
                return "finalize"
            if state.get("requires_tool"):
                return "agent_step"
            return "direct_answer"

        def route_after_agent(state: AgentGraphState) -> str:
            last_message = state["messages"][-1]
            if isinstance(last_message, AIMessage) and (
                getattr(last_message, "tool_calls", []) or []
            ):
                return "validate_tool_call"
            return "finalize"

        def route_after_validation(state: AgentGraphState) -> str:
            if state.get("tool_validation_failed"):
                return "agent_step"
            return "tool_node"

        graph.add_node("route_request", route_request)
        graph.add_node("direct_answer", direct_answer)
        graph.add_node("agent_step", agent_step)
        graph.add_node("validate_tool_call", validate_tool_call)
        graph.add_node("tool_node", tool_node)
        graph.add_node("finalize", finalize)

        graph.add_edge(START, "route_request")
        graph.add_conditional_edges(
            "route_request",
            route_after_router,
            {
                "direct_answer": "direct_answer",
                "agent_step": "agent_step",
                "finalize": "finalize",
            },
        )
        graph.add_conditional_edges(
            "agent_step",
            route_after_agent,
            {
                "validate_tool_call": "validate_tool_call",
                "finalize": "finalize",
            },
        )
        graph.add_conditional_edges(
            "validate_tool_call",
            route_after_validation,
            {
                "agent_step": "agent_step",
                "tool_node": "tool_node",
            },
        )
        graph.add_edge("tool_node", "agent_step")
        graph.add_edge("direct_answer", "finalize")
        graph.add_edge("finalize", END)

        return graph.compile()

    def _build_system_prompt(self, base_prompt: str, state: AgentGraphState) -> str:
        """Extend the base prompt with route-specific execution context."""
        route = state.get("route", "")
        prompt = base_prompt
        if route:
            prompt += self.tool_router.build_executor_context(route=route)
        prompt += self.tool_router.build_worker_context(
            worker=state.get("worker", ""),
            user_goal=state.get("user_goal", ""),
            entity_type=state.get("entity_type") or None,
            entity_name=state.get("entity_name") or None,
            time_period=state.get("time_period") or None,
            task_brief=state.get("task_brief", ""),
            missing_fields=state.get("missing_fields", []),
        )
        return prompt

    @staticmethod
    def _filter_tools_by_names(tools: List[Any], tool_names: List[str]) -> List[Any]:
        """Keep tools in original order while applying a whitelist."""
        allowed = set(tool_names)
        return [tool for tool in tools if getattr(tool, "name", None) in allowed]

    @staticmethod
    def _llm_model_name(llm: Any) -> str | None:
        """Return a provider model name from a LangChain chat model."""
        return getattr(llm, "model_name", None) or getattr(llm, "model", None)

    @staticmethod
    def _extract_last_human_message(messages: List[BaseMessage]) -> str:
        """Get the latest human message content from the state."""
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                content = getattr(msg, "content", "")
                if isinstance(content, str):
                    return content
        return ""

    @staticmethod
    def _extract_final_content(messages: List[BaseMessage]) -> str:
        """Find the last AI message that contains user-facing content."""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                content = getattr(msg, "content", "")
                if content and isinstance(content, str):
                    return content
        return ""

    @staticmethod
    def _format_messages_for_orchestrator(messages: List[BaseMessage]) -> str:
        """Format prior turns so the orchestrator can recover dialog state."""
        transcript: List[str] = []
        for msg in messages:
            content = getattr(msg, "content", "")
            if not isinstance(content, str) or not content.strip():
                continue
            if isinstance(msg, HumanMessage):
                transcript.append(f"Пользователь: {content}")
            elif isinstance(msg, AIMessage):
                transcript.append(f"Ассистент: {content}")
            elif isinstance(msg, ToolMessage):
                transcript.append(f"Инструмент: {content}")
        return "\n".join(transcript)
