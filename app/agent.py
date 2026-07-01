# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
import os
import json
import re
from zoneinfo import ZoneInfo
from typing import List, Optional, AsyncGenerator, Any
from pydantic import BaseModel, Field

from google.adk.workflow import Workflow, START, node, FunctionNode, Edge
from google.adk.agents import LlmAgent
from google.adk.tools import AgentTool
from google.adk.agents.context import Context
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.apps import App, ResumabilityConfig
from google.genai import types
from google.adk.models import Gemini
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

from .config import config

# -----------------------------------------------------------------------------
# 1. Pydantic Models for Schema Validation
# -----------------------------------------------------------------------------

class WorkflowInput(BaseModel):
    topics: str = Field(description="The topics to generate a podcast script for")

class WorkflowOutput(BaseModel):
    status: str = Field(description="The execution status: success or error")
    script: Optional[str] = Field(None, description="The final generated podcast script")
    message: str = Field(description="A user-friendly message or warning")

class PodcastState(BaseModel):
    topics: str = ""
    candidate_stories: str = ""
    approved_stories: str = ""
    feedback: str = ""
    final_script: str = ""
    security_passed: bool = False
    audit_log: List[str] = []

# -----------------------------------------------------------------------------
# 2. Sub-Agents & Orchestrator Definitions
# -----------------------------------------------------------------------------

# Initialize local MCP toolset running our custom FastMCP server
mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="uv",
            args=["run", "python", "-m", "app.mcp_server"],
        )
    )
)

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
import typing

class DemoModel(BaseLlm):
    model: str = "demo-offline-model"

    async def generate_content_async(self, llm_request: Any, stream: bool = False) -> typing.AsyncGenerator[LlmResponse, None]:
        # Identify the sub-agent calling based on its system instruction
        system_instruction = ""
        if hasattr(llm_request, "config") and llm_request.config:
            if hasattr(llm_request.config, "system_instruction") and llm_request.config.system_instruction:
                instr = llm_request.config.system_instruction
                if isinstance(instr, str):
                    system_instruction = instr
                elif hasattr(instr, "parts") and instr.parts:
                    system_instruction = " ".join([p.text for p in instr.parts if hasattr(p, "text") and p.text])
        
        # Identify the user's prompt
        prompt = ""
        if hasattr(llm_request, "contents") and llm_request.contents:
            last_content = llm_request.contents[-1]
            if hasattr(last_content, "parts") and last_content.parts:
                prompt = " ".join([p.text for p in last_content.parts if hasattr(p, "text") and p.text])

        # 1. Podcast Production Orchestrator logic
        if "Podcast Production Orchestrator" in system_instruction:
            # Check if there is a tool response in the history
            has_tool_response = False
            last_tool_name = ""
            for content in reversed(llm_request.contents):
                if hasattr(content, "parts") and content.parts:
                    for part in content.parts:
                        if hasattr(part, "function_response") and part.function_response:
                            has_tool_response = True
                            last_tool_name = part.function_response.name
                            break
                if has_tool_response:
                    break
            
            if has_tool_response:
                if last_tool_name == "news_researcher":
                    summary = (
                        "Here is the summarized list of tech stories:\n\n"
                        "- **Title:** Google Gemini 2.5 Flash Released\n"
                        "  **Summary:** Google launched Gemini 2.5 Flash with massive performance gains and low-latency API operations.\n"
                        "  **Key Takeaways:** Excellent for multi-agent workflows.\n\n"
                        "- **Title:** Astral uv Package Manager Updates\n"
                        "  **Summary:** uv package manager introduced project scaffolding and workspace management.\n"
                        "  **Key Takeaways:** Rust-based fast environment setups."
                    )
                    yield LlmResponse(content=types.Content(role='model', parts=[types.Part.from_text(text=summary)]))
                elif last_tool_name == "script_writer":
                    script = (
                        "[Upbeat Intro Music]\n"
                        "Host A: Welcome back to the podcast! Today we are discussing Gemini 2.5 and uv.\n"
                        "Host B: Yes, Gemini 2.5 Flash is incredibly fast, and uv simplifies Python development.\n"
                        "Host A: That is fantastic! See you next time.\n"
                        "[Upbeat Outro Music]"
                    )
                    yield LlmResponse(content=types.Content(role='model', parts=[types.Part.from_text(text=script)]))
                else:
                    yield LlmResponse(content=types.Content(role='model', parts=[types.Part.from_text(text="Execution completed.")]))
            else:
                # Decides tool routing
                if "conduct research" in prompt.lower() or "topics" in prompt.lower():
                    tool_call = types.Part(function_call=types.FunctionCall(
                        name="news_researcher",
                        args={"request": prompt}
                    ))
                    yield LlmResponse(content=types.Content(role='model', parts=[tool_call]))
                elif "write a podcast script" in prompt.lower() or "approved stories" in prompt.lower():
                    tool_call = types.Part(function_call=types.FunctionCall(
                        name="script_writer",
                        args={"request": prompt}
                    ))
                    yield LlmResponse(content=types.Content(role='model', parts=[tool_call]))
                else:
                    yield LlmResponse(content=types.Content(role='model', parts=[types.Part.from_text(text="I am ready to curate your podcast.")]))

        # 2. News Researcher logic
        elif "News Researcher" in system_instruction:
            summary = (
                "Here is the summarized list of tech stories:\n\n"
                "- **Title:** Google Gemini 2.5 Flash Released\n"
                "  **Summary:** Google launched Gemini 2.5 Flash with massive performance gains and low-latency API operations.\n"
                "  **Key Takeaways:** Excellent for multi-agent workflows.\n\n"
                "- **Title:** Astral uv Package Manager Updates\n"
                "  **Summary:** uv package manager introduced project scaffolding and workspace management.\n"
                "  **Key Takeaways:** Rust-based fast environment setups."
            )
            yield LlmResponse(content=types.Content(role='model', parts=[types.Part.from_text(text=summary)]))

        # 3. Script Writer logic
        elif "Podcast Script Writer" in system_instruction:
            script = (
                "[Upbeat Intro Music]\n"
                "Host A: Welcome back to the podcast! Today we are discussing Gemini 2.5 and uv.\n"
                "Host B: Yes, Gemini 2.5 Flash is incredibly fast, and uv simplifies Python development.\n"
                "Host A: That is fantastic! See you next time.\n"
                "[Upbeat Outro Music]"
            )
            yield LlmResponse(content=types.Content(role='model', parts=[types.Part.from_text(text=script)]))

        # 4. General fallback
        else:
            yield LlmResponse(content=types.Content(role='model', parts=[types.Part.from_text(text="Demo offline model response.")]))

# Instantiate DemoModel instead of Gemini to run fully local/free
model_instance = DemoModel()


news_researcher = LlmAgent(
    name="news_researcher",
    model=model_instance,
    instruction=(
        "You are a professional News Researcher for a popular technology podcast. "
        "Your task is to search for real news and articles about the requested topics and produce a clear, summarized list of stories. "
        "Use the fetch_news_headlines and parse_article_content tools to gather news articles. "
        "For each story, provide:\n"
        "- Title\n"
        "- Summary of the main event or facts\n"
        "- Key takeaways\n"
        "If there are no search tools available, simulate realistic, high-quality current stories based on your knowledge base."
    ),
    description="Fetches and summarizes recent news articles on given topics.",
    tools=[mcp_toolset]
)

script_writer = LlmAgent(
    name="script_writer",
    model=model_instance,
    instruction=(
        "You are a creative Podcast Script Writer. "
        "Your task is to take approved news summaries and draft a highly engaging, conversational script for two co-hosts:\n"
        "- Host A: Curious, asks thoughtful questions, acts as the guide.\n"
        "- Host B: Knowledgeable tech expert, explains complex concepts simply.\n"
        "Format the script clearly with headers, sound effect cues in square brackets (e.g. [Upbeat Intro Music]), and host dialogue.\n"
        "After drafting the script, call the save_podcast_draft tool to save it as 'script_draft.txt'. "
        "If the user has provided specific feedback or revision requests, make sure to address them in the script draft."
    ),
    description="Drafts conversational podcast dialog scripts for Host A and Host B from news summaries.",
    tools=[mcp_toolset]
)

orchestrator = LlmAgent(
    name="orchestrator",
    model=model_instance,
    instruction=(
        "You are the Podcast Production Orchestrator. "
        "You coordinate the podcast script generation process. "
        "You have access to two sub-agents as tools:\n"
        "1. news_researcher: Call this tool when you need news gathered and summarized on topics.\n"
        "2. script_writer: Call this tool when you need approved summaries compiled into a conversational script.\n"
        "Analyze the user's request. If they want news topics researched, use news_researcher. If they want a script generated from summaries, use script_writer. "
        "Deliver the output of the sub-agent clearly."
    ),
    tools=[AgentTool(news_researcher), AgentTool(script_writer)]
)

# -----------------------------------------------------------------------------
# 3. Workflow Nodes
# -----------------------------------------------------------------------------

@node
async def security_checkpoint(ctx: Context, node_input: Any):
    # Extract topics text safely from node_input (could be types.Content or str)
    topics = ""
    if isinstance(node_input, str):
        topics = node_input
    elif hasattr(node_input, "parts") and node_input.parts:
        parts_text = []
        for part in node_input.parts:
            if hasattr(part, "text") and part.text:
                parts_text.append(part.text)
        topics = " ".join(parts_text)
    elif isinstance(node_input, dict):
        topics = node_input.get("topics", str(node_input))
    else:
        topics = str(node_input)
        
    ctx.state["topics"] = topics
    ctx.state.setdefault("audit_log", [])
    
    # PII Scrubbing
    scrubbed_topics = topics
    pii_found = False
    
    email_pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    if re.search(email_pattern, topics):
        scrubbed_topics = re.sub(email_pattern, "[REDACTED_EMAIL]", scrubbed_topics)
        pii_found = True
        
    phone_pattern = r'\+?\d{1,4}?[-.\s]?\(?\d{1,3}?\)?[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}'
    if re.search(phone_pattern, topics) and len(re.sub(r'\D', '', topics)) >= 7:
        scrubbed_topics = re.sub(phone_pattern, "[REDACTED_PHONE]", scrubbed_topics)
        pii_found = True
        
    if pii_found:
        audit_entry = {
            "timestamp": datetime.datetime.now(ZoneInfo("UTC")).isoformat(),
            "node": "security_checkpoint",
            "severity": "WARNING",
            "message": "PII detected and scrubbed.",
            "original": topics,
            "scrubbed": scrubbed_topics
        }
        ctx.state["audit_log"].append(json.dumps(audit_entry))
        ctx.state["topics"] = scrubbed_topics
        
    # Prompt Injection Check
    injection_found = False
    injection_keywords = [
        "ignore previous instructions", "system prompt", "override instructions",
        "you must override", "jailbreak", "dan mode", "ignore all instructions",
        "developer mode"
    ]
    for kw in injection_keywords:
        if kw in topics.lower():
            injection_found = True
            break
            
    if injection_found:
        audit_entry = {
            "timestamp": datetime.datetime.now(ZoneInfo("UTC")).isoformat(),
            "node": "security_checkpoint",
            "severity": "CRITICAL",
            "message": "Prompt injection attempt detected.",
            "input": topics
        }
        ctx.state["audit_log"].append(json.dumps(audit_entry))
        return Event(route="SECURITY_EVENT")
        
    # Domain-Specific Rule: Reject fake news or illegal request
    inappropriate_found = False
    restricted_keywords = ["fake news", "slander", "libel", "illegal hacking", "how to hack"]
    for kw in restricted_keywords:
        if kw in topics.lower():
            inappropriate_found = True
            break
            
    if inappropriate_found:
        audit_entry = {
            "timestamp": datetime.datetime.now(ZoneInfo("UTC")).isoformat(),
            "node": "security_checkpoint",
            "severity": "CRITICAL",
            "message": "Restricted domain topic requested.",
            "input": topics
        }
        ctx.state["audit_log"].append(json.dumps(audit_entry))
        return Event(route="SECURITY_EVENT")
        
    # Success Log
    audit_entry = {
        "timestamp": datetime.datetime.now(ZoneInfo("UTC")).isoformat(),
        "node": "security_checkpoint",
        "severity": "INFO",
        "message": "Security check passed.",
        "input": scrubbed_topics
    }
    ctx.state["audit_log"].append(json.dumps(audit_entry))
    
    return Event(route="safe", state={"topics": scrubbed_topics, "security_passed": True})


@node(rerun_on_resume=True)
async def research_node(ctx: Context, node_input: Any):
    topics = ctx.state.get("topics", "")
    prompt = f"Conduct research on these topics: {topics}. Call the news_researcher sub-agent tool to get the research summary."
    
    response = await ctx.run_node(orchestrator, node_input=prompt)
    
    text_output = ""
    if hasattr(response, "parts") and response.parts:
        text_output = response.parts[0].text
    elif isinstance(response, str):
        text_output = response
        
    return Event(output=text_output, state={"candidate_stories": text_output})


@node(rerun_on_resume=True)
async def human_review_node(ctx: Context, node_input: str):
    if ctx.resume_inputs and "review_response" in ctx.resume_inputs:
        user_input = ctx.resume_inputs["review_response"]
        
        audit_entry = {
            "timestamp": datetime.datetime.now(ZoneInfo("UTC")).isoformat(),
            "node": "human_review",
            "decision": "resume",
            "user_response": user_input
        }
        ctx.state.setdefault("audit_log", []).append(json.dumps(audit_entry))
        
        if "yes" in user_input.lower() or "approve" in user_input.lower() or "proceed" in user_input.lower():
            yield Event(
                output=ctx.state.get("candidate_stories", ""),
                route="approved",
                state={"approved_stories": ctx.state.get("candidate_stories", "")}
            )
            return
        else:
            yield Event(
                output=user_input,
                route="revision",
                state={"feedback": user_input}
            )
            return
            
    candidate_stories = ctx.state.get("candidate_stories", "")
    yield RequestInput(
        interrupt_id="review_response",
        message=(
            f"Here are the research summaries gathered for your topics:\n\n"
            f"{candidate_stories}\n\n"
            f"Would you like to generate the script from these? "
            f"Reply 'yes' to proceed, or provide feedback/revisions to adjust the research."
        )
    )


@node(rerun_on_resume=True)
async def generate_script_node(ctx: Context, node_input: str):
    approved = ctx.state.get("approved_stories", "")
    feedback = ctx.state.get("feedback", "")
    prompt = f"Write a podcast script based on these approved stories:\n\n{approved}\n\n"
    if feedback:
        prompt += f"Ensure you address this user feedback: {feedback}\n\n"
    prompt += "Call the script_writer sub-agent tool to draft the conversational dialog script."
    
    response = await ctx.run_node(orchestrator, node_input=prompt)
    
    text_output = ""
    if hasattr(response, "parts") and response.parts:
        text_output = response.parts[0].text
    elif isinstance(response, str):
        text_output = response
        
    return Event(output=text_output, state={"final_script": text_output})


@node
async def security_failure_node(ctx: Context, node_input: Any):
    msg = "Security Checkpoint Failed: PII detected, prompt injection detected, or topic restricted."
    yield Event(
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(text=f"⚠️ {msg}")]
        )
    )
    yield Event(
        output=WorkflowOutput(status="error", message=msg)
    )


@node
async def final_output_node(ctx: Context, node_input: Any):
    script = ctx.state.get("final_script", "")
    yield Event(
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(text=f"Here is your completed podcast script:\n\n{script}")]
        )
    )
    yield Event(
        output=WorkflowOutput(status="success", script=script, message="Script generated successfully.")
    )

# -----------------------------------------------------------------------------
# 4. Workflow Definition
# -----------------------------------------------------------------------------

root_agent = Workflow(
    name="podcast_script_curator_workflow",
    edges=[
        Edge(from_node=START, to_node=security_checkpoint),
        Edge(from_node=security_checkpoint, to_node=research_node, route="safe"),
        Edge(from_node=security_checkpoint, to_node=security_failure_node, route="SECURITY_EVENT"),
        Edge(from_node=research_node, to_node=human_review_node),
        Edge(from_node=human_review_node, to_node=research_node, route="revision"),
        Edge(from_node=human_review_node, to_node=generate_script_node, route="approved"),
        Edge(from_node=generate_script_node, to_node=final_output_node),
        Edge(from_node=security_failure_node, to_node=final_output_node),
    ],
    input_schema=None,
    output_schema=WorkflowOutput,
    state_schema=PodcastState,
)

app = App(
    root_agent=root_agent,
    name="app",
    resumability_config=ResumabilityConfig(is_resumable=True)
)
