# Workflow Steps — Complete Reference

## Step Types

### `@step` — Standard Step

Executes business logic as an atomic unit. On failure, the workflow enters Failed state.

```python
from orchestrator.workflow import step
from orchestrator.types import State

@step("Create port in network")
def create_port_in_network(
    subscription: ServicePortProvisioning,
    customer_id: str,
) -> State:
    external_id = network_api.create_port(
        name=subscription.port_block.port_name,
        customer=customer_id,
    )
    subscription.port_block.external_id = external_id
    return {"subscription": subscription}
```

Return a dict of state updates (merged into workflow state), or `None` if no state changes.

### `@retrystep` — Recoverable Failures

For operations that may fail transiently (network timeouts, service unavailability). On failure, the process goes to WAITING state and is periodically retried.

```python
from orchestrator.workflow import retrystep

@retrystep("Push configuration to device")
def push_config(subscription: ServicePortProvisioning) -> State:
    try:
        device_api.push(subscription)
        return {"config_pushed": True}
    except TransientError:
        raise  # Will be retried automatically
    except PermanentError as e:
        raise ProcessFailureError(f"Cannot push config: {e}") from e
```

Distinguish transient from permanent errors — permanent errors should raise `ProcessFailureError` to halt the workflow rather than retry indefinitely.

### `@inputstep` — User Input Mid-Workflow

Pauses the workflow and presents a form to a user or team. The workflow resumes when the form is submitted.

```python
from orchestrator.workflow import inputstep
from orchestrator.config.assignee import Assignee
from orchestrator.forms import FormPage

@inputstep("Confirm deletion", assignee=Assignee.NOC)
def confirm_deletion(subscription: ServicePort) -> FormGenerator:
    class ConfirmForm(FormPage):
        class Config:
            title = f"Delete {subscription.description}?"
        confirm: bool

    user_input = yield ConfirmForm
    return user_input.model_dump()
```

**Critical**: Input steps must be side-effect free. They are not executed by the workflow engine — they only define what form to show. Never call APIs, modify data, or perform I/O in an input step.

**Assignee options**:
- `Assignee.SYSTEM` — Automated (no human approval)
- `Assignee.NOC` — NOC team
- `Assignee("team_name")` — Specific team

### `callback_step` — Long-Running External Operations

For operations that take significant time (Ansible playbooks, Terraform applies). Triggers an external operation and waits for a callback.

```python
from orchestrator.workflow import callback_step

# Action: triggers the external operation
@step("Trigger ansible playbook")
def trigger_ansible(
    subscription: ServicePortProvisioning,
    callback_route: str,  # Injected automatically by orchestrator
) -> State:
    callback_url = f"http://orchestrator-host{callback_route}"
    response = requests.post("http://ansible-proxy/api/run", json={
        "playbook": "provision_port.yml",
        "callback": callback_url,
        "vars": {"port_id": str(subscription.port_block.port_id)},
    })
    response.raise_for_status()
    return {"job_id": response.json()["id"]}

# Validate: processes the callback result
@step("Validate ansible result")
def validate_ansible(callback_result: dict) -> State:
    if callback_result.get("return_code") != 0:
        raise ProcessFailureError(
            message="Ansible playbook failed",
            details=callback_result,
        )
    return {"ansible_output": callback_result}

# Wire them together
@create_workflow(initial_input_form=form_gen)
def create_service_port() -> StepList:
    return (
        begin
        >> construct_subscription
        >> store_process_subscription()
        >> callback_step(
            name="Execute Playbook",
            action_step=trigger_ansible,
            validate_step=validate_ansible,
        )
        >> finalize
    )
```

The external system calls `{callback_route}` with the result when done. Progress updates can be sent to `{callback_route}/progress`.

### `step_group` — Logical Grouping

Group related steps into a single visual unit. If any sub-step fails, the entire group fails but can resume from the last failed sub-step.

```python
from orchestrator.workflow import step_group

provision_steps = step_group(
    name="Provision Infrastructure",
    steps=(
        begin
        >> create_in_network
        >> configure_firewall
        >> verify_connectivity
    ),
)

@create_workflow(initial_input_form=form_gen)
def create_service() -> StepList:
    return begin >> initialize >> provision_steps >> activate
```

### `conditional` — Predicate-Based Execution

Skip steps based on a state predicate. The predicate receives the current state and returns a boolean.

```python
from orchestrator.workflow import conditional

def needs_nat(state: State) -> bool:
    return state.get("enable_nat", False)

@create_workflow(initial_input_form=form_gen)
def create_service() -> StepList:
    return (
        begin
        >> setup_basic
        >> conditional(needs_nat)(
            begin >> configure_nat >> test_nat
        )
        >> finalize
    )
```

## Workflow Decorators — Detailed Usage

### `@create_workflow`

```python
from orchestrator.workflows.utils import create_workflow
from orchestrator.types import SubscriptionLifecycle

@create_workflow(
    initial_input_form=initial_input_form_generator,
    status=SubscriptionLifecycle.ACTIVE,  # Final status (default: ACTIVE)
)
def create_service_port() -> StepList:
    return begin >> construct_model >> store_process_subscription() >> provision
```

Auto-provides in state: `product` (UUID), `product_name` (str), plus form data.

### `@modify_workflow`

```python
from orchestrator.workflows.utils import modify_workflow

@modify_workflow(initial_input_form=modify_form_generator)
def modify_service_port() -> StepList:
    return begin >> update_fields >> reprovision
```

Auto-provides in state: `subscription_id`, `product`, `customer_id`, `subscription` (loaded model), plus form data.

### `@terminate_workflow`

```python
from orchestrator.workflows.utils import terminate_workflow

@terminate_workflow(initial_input_form=terminate_form_generator)
def terminate_service_port() -> StepList:
    return begin >> deprovision >> cleanup_external_systems
```

Automatically sets status to TERMINATED after custom steps.

### `@validate_workflow`

```python
from orchestrator.workflows.utils import validate_workflow

@validate_workflow()
def validate_service_port() -> StepList:
    return begin >> load_state >> check_external_system >> check_database
```

Uses `unsync_unchecked` (allows validation even if subscription is out of sync).

### `@task`

```python
from orchestrator.workflows.utils import task

@task()
def task_cleanup_old_processes() -> StepList:
    return begin >> find_old_processes >> delete_old_processes
```

Target is `Target.SYSTEM`. Not tied to a specific product.

## Run Predicates

Block workflow execution based on conditions:

```python
from orchestrator.workflow import RunPredicatePass, RunPredicateFail

def only_during_maintenance(context: PredicateContext) -> RunPredicateResult:
    if is_maintenance_window():
        return RunPredicatePass()
    return RunPredicateFail("Only allowed during maintenance window (02:00-06:00)")

@create_workflow(
    initial_input_form=form_gen,
    run_predicate=only_during_maintenance,
)
def create_critical_service() -> StepList:
    return begin >> provision
```

API responses when predicate fails:
- REST: HTTP 412 Precondition Failed
- GraphQL: MutationError
- Scheduler: Logs and skips

## Built-In Steps

| Step | Purpose |
|------|---------|
| `begin` | Empty StepList starting point for `>>` composition |
| `init` | Workflow start marker (added by decorators) |
| `done` | Workflow end marker (added by decorators) |
| `unsync` | Mark subscription out-of-sync (locks it) |
| `resync` | Mark subscription in-sync (unlocks it) |
| `set_status(lifecycle)` | Change subscription lifecycle state |
| `store_process_subscription()` | Link process record to subscription |
| `refresh_subscription_search_index` | Update search index for subscription |
| `refresh_process_search_index` | Update search index for process |

## Process States

Steps produce process state variants:

| State | Meaning | Next Action |
|-------|---------|-------------|
| `Success(state)` | Step completed, continue | Next step |
| `Skipped(state)` | Conditional step skipped | Next step |
| `Suspend(state)` | Waiting for user input (`@inputstep`) | User submits form |
| `Waiting(state)` | Retry pending (`@retrystep` failure) | Auto-retry |
| `AwaitingCallback(state)` | Waiting for external callback | Callback arrives |
| `Abort(state)` | Workflow aborted | Terminal |
| `Failed(state)` | Step failed | Manual intervention |
| `Complete(state)` | Workflow finished | Terminal |

## Reusable Steps with singledispatch

Use `functools.singledispatch` to write steps that behave differently per product type:

```python
from functools import singledispatch

@singledispatch
def provision(model: SubscriptionModel) -> str:
    raise NotImplementedError(f"No provisioning for {type(model)}")

@provision.register
def _(model: ServicePort) -> str:
    return network_api.create_port(model)

@provision.register
def _(model: L2VPN) -> str:
    return vpn_api.create_circuit(model)

@step("Provision in external system")
def provision_step(subscription: SubscriptionModel) -> State:
    external_id = provision(subscription)
    return {"external_id": external_id}
```

## Workflow Configuration

### Usable States

Control which subscription lifecycle states allow a workflow:

```python
from orchestrator.services.subscriptions import WF_USABLE_MAP

WF_USABLE_MAP.update({
    "modify_service_port": ["active", "provisioning"],
    "validate_service_port": ["active"],
})
```

### Blocked by In-Use Subscriptions

Prevent modification when other subscriptions depend on this one:

```python
from orchestrator.services.subscriptions import WF_BLOCKED_BY_IN_USE_BY_SUBSCRIPTIONS

WF_BLOCKED_BY_IN_USE_BY_SUBSCRIPTIONS.update({
    "modify_service_port": True,
})
```

### Allow While Out-of-Sync

By default, only tasks run on out-of-sync subscriptions:

```python
from orchestrator.services.subscriptions import WF_USABLE_WHILE_OUT_OF_SYNC

WF_USABLE_WHILE_OUT_OF_SYNC.extend(["modify_description"])
```
