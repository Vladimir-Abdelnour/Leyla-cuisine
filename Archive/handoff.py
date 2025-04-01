from rich.prompt import Prompt
from agents import (
    Agent,
    Runner,
    AsyncOpenAI,
    OpenAIResponsesModel,
    RunContextWrapper,
    handoff,
    function_tool
)
from pydantic import BaseModel, Field


# Define a Pydantic model for handoff data
class RefundReason(BaseModel):
    reason: str = Field(..., description="Reason for the refund")


# Create an instance of the LLM model
llm_model = OpenAIResponsesModel(
    model="gpt-4o-mini",        # adjust model name as needed
    openai_client=AsyncOpenAI()
)


# Define a callback function that triggers on handoff
def on_handoff_trigger(ctx: RunContextWrapper, input_data: RefundReason):
    print("Handoff called")
    print("Context:", ctx)
    print("Input:", input_data)


# Define functions (tools) using the @function_tool decorator
@function_tool
def refund_status() -> bool:
    """Check if the refund is issued."""
    # Replace with real logic if needed
    return True


@function_tool
def check_balance_due() -> float:
    """Check the balance due."""
    # Replace with real logic if needed
    return 100.0


# Create agents
refund_agent = Agent(
    name="Refund agent",
    instructions="You are an agent that checks the refund status.",
    model=llm_model,
    output_type=str,
    tools=[refund_status]
)

balance_due_agent = Agent(
    name="Balance Due agent",
    instructions="You are an agent that checks the balance due.",
    model=llm_model,
    output_type=str,
    tools=[check_balance_due]
)

my_agent = Agent(
    name="Customer agent",
    instructions="You are a customer service agent.",
    model=llm_model,
    output_type=str,
    handoffs=[
        handoff(
            agent=refund_agent,
            on_handoff=on_handoff_trigger,
            input_type=RefundReason
        )
    ]
)

# Set up cross-handoffs among agents
balance_due_agent.handoffs.append(my_agent)
balance_due_agent.handoffs.append(refund_agent)
refund_agent.handoffs.append(my_agent)
refund_agent.handoffs.append(balance_due_agent)

# Conversation loop
conversation = []
active_agent = my_agent

while True:
    user_input = Prompt.ask("User")
    if user_input.lower() in ["exit", "quit"]:
        raise Exception("Exiting the conversation.")

    conversation.append({"role": "user", "content": user_input})

    response = Runner.run_sync(
        starting_agent=active_agent,
        input=conversation
    )

    # The runner returns the agent that ended up responding
    active_agent = response.last_agent

    # Convert the entire conversation into a list suitable for the next turn
    conversation = response.to_input_list()

    print(f"{active_agent.name}:", response.final_output)
