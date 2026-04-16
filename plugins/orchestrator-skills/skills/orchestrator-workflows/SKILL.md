---
name: orchestrator-workflows
description: "This skill should be used when the user asks to \"create a workflow\", \"write a create workflow\", \"add a modify workflow\", \"build a terminate workflow\", \"define an input form\", \"add a workflow step\", \"use FormGenerator\", \"yield a form page\", or mentions orchestrator-core workflow concepts like StepList, FormPage, inputstep, retrystep, callbacks, domain models, product blocks, subscription lifecycle, or LazyWorkflowInstance. Also use when the user asks how workflows work, needs to understand the generator DSL, wants to add steps to an existing workflow, or is implementing business logic in generated workflow scaffolding."
---

# Orchestrator-Core Workflows

Workflows are the execution engine of orchestrator-core. They combine input forms, sequential steps, and domain model lifecycle transitions to manage subscriptions end-to-end.

## Core Pattern

Every workflow has three parts: an **input form** (collects user data), a **step list** (executes business logic), and a **workflow decorator** (handles lifecycle boilerplate).

```python
from orchestrator.workflow import StepList, begin, step
from orchestrator.workflows.utils import create_workflow

def initial_input_form_generator(product_name: str) -> FormGenerator:
    class CreateForm(FormPage):
        customer_id: CustomerId
        port_name: str

    user_input = yield CreateForm
    return user_input.model_dump()

@create_workflow(initial_input_form=initial_input_form_generator)
def create_service_port() -> StepList:
    return (
        begin
        >> construct_subscription
        >> store_process_subscription()
        >> provision_in_external_system
    )
```

## Workflow Types

| Decorator | Target | Use Case | Auto-wraps with |
|-----------|--------|----------|----------------|
| `@create_workflow` | CREATE | New subscription | `init`, `store_process_subscription()`, `set_status(ACTIVE)`, `resync`, `done` |
| `@modify_workflow` | MODIFY | Change subscription | `init`, `store_process_subscription()`, `unsync`, ..., `resync`, `done` |
| `@terminate_workflow` | TERMINATE | Remove subscription | `init`, `store_process_subscription()`, `unsync`, ..., `set_status(TERMINATED)`, `resync`, `done` |
| `@validate_workflow` | VALIDATE | Check consistency | `init`, `store_process_subscription()`, `unsync_unchecked`, ..., `resync`, `done` |
| `@reconcile_workflow` | RECONCILE | Sync external systems | `init`, `store_process_subscription()`, `unsync`, ..., `resync`, `done` |
| `@task` | SYSTEM | Background/scheduled job | `init`, ..., `done` |

Each decorator automatically adds the steps shown — only define custom business logic steps. Read `references/workflow-steps.md` for detailed usage of each decorator and all step types.

## Step Types — Quick Reference

```python
@step("Step Name")                           # Standard step, fails on error
def my_step(field: str) -> State:
    return {"result": process(field)}

@retrystep("Flaky Operation")               # Auto-retries on failure
def call_external(subscription: Model) -> State:
    api.provision(subscription)
    return {}

@inputstep("Approve", assignee=Assignee.NOC) # Pauses for user input
def get_approval(subscription: Model) -> FormGenerator:
    class ApproveForm(FormPage):
        approved: bool
    user_input = yield ApproveForm
    return user_input.model_dump()
```

Read `references/workflow-steps.md` for the complete step type reference including `callback_step`, `step_group`, and `conditional`.

## Input Forms (Generator DSL)

Forms use Python generators. `yield` pauses the workflow to show a form; the user's response comes back as the yield result.

```python
from orchestrator.forms import FormPage
from orchestrator.types import FormGenerator

def initial_input_form_generator(product_name: str) -> FormGenerator:
    # Page 1
    class BasicInfo(FormPage):
        customer_id: CustomerId
        description: str

    page1 = yield BasicInfo

    # Page 2 (can use page1 data for dynamic choices)
    class Details(FormPage):
        bandwidth: int
        vlan_id: int

    page2 = yield Details
    return {**page1.model_dump(), **page2.model_dump()}
```

Read `references/forms-and-state.md` for multi-page forms, dynamic dropdowns, form wrapping, validators, and state injection.

## Domain Models & Lifecycle

Domain models have lifecycle variants enforcing field requirements at each stage:

```python
class PortBlockInactive(ProductBlockModel, product_block_name="Port"):
    port_name: str | None = None      # Optional in INITIAL
    port_speed: int | None = None

class PortBlockProvisioning(PortBlockInactive, lifecycle=[SubscriptionLifecycle.PROVISIONING]):
    port_name: str                     # Required from PROVISIONING
    port_speed: int | None = None

class PortBlock(PortBlockProvisioning, lifecycle=[SubscriptionLifecycle.ACTIVE]):
    port_name: str
    port_speed: int                    # Required from ACTIVE
```

Transition between lifecycle stages in steps:

```python
@step("Activate")
def activate(subscription: PortProvisioning) -> State:
    subscription = Port.from_other_lifecycle(subscription, SubscriptionLifecycle.ACTIVE)
    return {"subscription": subscription}
```

Read `references/domain-models.md` for the complete domain model reference including subscription models, nested blocks, and database loading.

## State Injection

Step functions declare parameters that are automatically extracted from the workflow state dict. Type hints drive deserialization:

```python
@step("Process")
def my_step(
    product: UUID,                    # From state["product"]
    subscription: MyModel,            # Loaded from DB via state["subscription"]
    customer_id: str,                 # From state["customer_id"]
    count: int = 5,                   # Default if not in state
) -> State:
    return {"result": "value"}        # Merged back into state
```

**Critical rule**: Domain models must be returned in state for changes to persist:

```python
# WRONG — changes lost
@step("Update")
def update(subscription: MyModel) -> State:
    subscription.field = "new"
    return {}                         # subscription not returned!

# CORRECT
@step("Update")
def update(subscription: MyModel) -> State:
    subscription.field = "new"
    return {"subscription": subscription}
```

## Workflow Registration

After creating workflow files, register them for the orchestrator to discover:

### 1. Add LazyWorkflowInstance

In `workflows/__init__.py`:

```python
from orchestrator.workflows import LazyWorkflowInstance

LazyWorkflowInstance(".service_port.create_service_port", "create_service_port")
LazyWorkflowInstance(".service_port.modify_service_port", "modify_service_port")
LazyWorkflowInstance(".service_port.terminate_service_port", "terminate_service_port")
LazyWorkflowInstance(".service_port.validate_service_port", "validate_service_port")
```

### 2. Generate Database Migration

```bash
python main.py db migrate-workflows "add service port workflows"
python main.py db upgrade heads
```

## Common Mistakes

1. **Not returning domain models** — Changes to subscription objects are lost unless returned in state dict
2. **Side effects in `@inputstep`** — Input steps define forms only; they do not execute in the engine. Never call APIs or modify data in them
3. **Wrong lifecycle variant** — Accepting `MyModel` (Active) when the subscription is still in PROVISIONING state causes validation errors. Match the parameter type to the expected lifecycle stage
4. **Missing `unsync`/`resync`** — The workflow decorators handle this automatically, but custom `@workflow` definitions must manage sync state manually
5. **Forgetting to register** — New workflows need both a `LazyWorkflowInstance` entry and a database migration

## Reference Files

- **`references/workflow-steps.md`** — Complete step type reference: `@step`, `@retrystep`, `@inputstep`, `callback_step`, `step_group`, `conditional`, run predicates, and all built-in steps
- **`references/forms-and-state.md`** — Input form patterns: multi-page forms, dynamic dropdowns, form wrapping, validators, state injection, and supported container types
- **`references/domain-models.md`** — Domain model lifecycle: ProductBlockModel, SubscriptionModel, lifecycle transitions, nested blocks, `from_subscription`, and `from_other_lifecycle`
