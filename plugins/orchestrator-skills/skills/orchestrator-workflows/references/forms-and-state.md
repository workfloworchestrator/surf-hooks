# Input Forms & State — Complete Reference

## Form Generator Pattern

Forms use Python generators. Each `yield` pauses the workflow to display a form page; the user's response is returned as the yield result.

```python
from orchestrator.forms import FormPage
from orchestrator.types import FormGenerator

def initial_input_form_generator(product_name: str) -> FormGenerator:
    class MyForm(FormPage):
        field_name: str
        field_count: int

    user_input = yield MyForm
    return user_input.model_dump()
```

The return value is merged into the workflow state dict.

## Multi-Page Forms

Chain multiple yields for wizard-style multi-page forms:

```python
def multi_page_form(product_name: str) -> FormGenerator:
    class Page1(FormPage):
        class Config:
            title = "Basic Information"
        customer_id: CustomerId
        description: str

    page1 = yield Page1

    # Page 2 can use data from page 1
    class Page2(FormPage):
        class Config:
            title = f"Details for {page1.description}"
        bandwidth: int
        vlan_id: int

    page2 = yield Page2

    return {**page1.model_dump(), **page2.model_dump()}
```

## Form Wrapping

The orchestrator wraps initial input forms to add standard pages (product/subscription selection).

### Create Workflows

```python
from orchestrator.forms import wrap_create_initial_input_form

@create_workflow(
    initial_input_form=wrap_create_initial_input_form(initial_input_form_generator)
)
def create_service() -> StepList: ...
```

The wrapper adds a product selection page before the custom form. State automatically includes:
- `product` — Product UUID
- `product_name` — Product name string

### Modify/Terminate Workflows

```python
from orchestrator.forms import wrap_modify_initial_input_form

@modify_workflow(
    initial_input_form=wrap_modify_initial_input_form(modify_form_generator)
)
def modify_service() -> StepList: ...
```

The wrapper adds a subscription selection page. State automatically includes:
- `subscription_id` — Subscription UUID
- `product` — Product UUID
- `customer_id` — Customer identifier
- `subscription` — Loaded domain model instance

## Dynamic Dropdown Choices

Create selection fields populated from the database:

```python
from orchestrator.forms.validators import Choice, choice_list
from orchestrator.db import db
from orchestrator.db.models import SubscriptionTable, ProductTable
from sqlalchemy import select

def get_port_choices() -> list:
    stmt = (
        select(SubscriptionTable)
        .join(ProductTable)
        .filter(
            ProductTable.product_type == "ServicePort",
            SubscriptionTable.status == "active",
        )
    )
    subscriptions = db.session.scalars(stmt).all()

    return choice_list(
        Choice(
            "PortChoice",
            zip(
                [str(sub.subscription_id) for sub in subscriptions],
                [sub.description for sub in subscriptions],
            ),
        ),
        min_items=1,
        max_items=1,
    )

def form_generator(product_name: str) -> FormGenerator:
    class SelectPortForm(FormPage):
        port: get_port_choices()

    data = yield SelectPortForm
    return data.model_dump()
```

The `choice_list` function returns a Pydantic-compatible type that renders as a dropdown. The result is a list of selected UUIDs.

## Form Validators

### Field-Level Validation (AfterValidator)

```python
from pydantic import AfterValidator
from typing import Annotated

def validate_port_name(value: str) -> str:
    if not value.startswith("eth"):
        raise ValueError("Port name must start with 'eth'")
    return value

ValidPortName = Annotated[str, AfterValidator(validate_port_name)]

class CreateForm(FormPage):
    port_name: ValidPortName
```

### Model-Level Validation (model_validator)

```python
from pydantic import model_validator

class CreateCircuitForm(FormPage):
    endpoint_a: UUID
    endpoint_b: UUID

    @model_validator(mode="after")
    def endpoints_must_differ(self) -> "CreateCircuitForm":
        if self.endpoint_a == self.endpoint_b:
            raise ValueError("Endpoints cannot be on the same node")
        return self
```

### Generated Validators

The CLI generator creates skeleton validators from YAML `validations`:

```python
# In shared/forms.py (generated)
def must_be_unused_to_change_mode_validator(value: str) -> str:
    # TODO: implement validation
    return value

validated_port_mode = Annotated[PortMode, AfterValidator(must_be_unused_to_change_mode_validator)]
```

## Common Form Field Types

```python
from orchestrator.forms import FormPage
from orchestrator.forms.validators import (
    CustomerId,      # Customer selection dropdown
    DisplaySubscription,  # Read-only subscription display
    Label,           # Read-only label text
    LongText,        # Multi-line text area
    ReadOnlyField,   # Non-editable field showing current value
    Divider,         # Visual separator
)

class ExampleForm(FormPage):
    customer: CustomerId                           # Customer picker
    description: str                               # Text input
    notes: LongText                                # Textarea
    current_status: ReadOnlyField("active")        # Read-only display
    bandwidth: int                                 # Number input
    enabled: bool = True                           # Checkbox with default
```

## Modify Workflow Forms

Modify forms typically show current values as read-only and allow editing of modifiable fields:

```python
def modify_form_generator(subscription_id: UUIDstr) -> FormGenerator:
    subscription = ServicePort.from_subscription(subscription_id)

    class ModifyForm(FormPage):
        # Read-only fields
        port_name: ReadOnlyField(subscription.port_block.port_name)

        # Modifiable fields (pre-populated with current values)
        description: str = subscription.description
        bandwidth: int = subscription.port_block.bandwidth

    user_input = yield ModifyForm
    return user_input.model_dump()
```

## State Injection

Step functions declare parameters that are automatically extracted from the workflow state dict.

### How It Works

1. The orchestrator inspects the function's type hints
2. For each parameter, it looks up `state[param_name]`
3. Values are deserialized based on the type hint
4. Domain model types trigger database loading

### Type Hint Mapping

| Type Hint | Behavior |
|-----------|----------|
| `str`, `int`, `bool` | Direct extraction from state |
| `UUID` | Converted from string |
| `MyModel` (SubscriptionModel) | Loaded from DB via `state["my_model"]` UUID |
| `list[MyModel]` | Each element loaded from DB |
| `Optional[MyModel]` | `None` if not in state |
| `datetime` | Parsed from ISO format |
| `Enum` | Constructed from value |

### Default Values

Parameters with defaults are optional — they use the default if the key is missing from state:

```python
@step("Process")
def process(
    subscription: MyModel,     # Required in state
    retries: int = 0,          # Optional, defaults to 0
    notes: str | None = None,  # Optional, defaults to None
) -> State:
    return {"retries": retries + 1}
```

### What Gets Provided Automatically

**Create workflows**: `product` (UUID), `product_name` (str), `organisation` (UUID)
**Modify/terminate**: `subscription_id` (UUID), `product` (UUID), `customer_id` (str), `subscription` (model)
**All workflows**: `process_id` (UUID) — the running process ID

### State Dict Contents

State is a `dict[str, Any]` serialized as JSON between steps. Keep values JSON-serializable:
- Primitives: `str`, `int`, `float`, `bool`, `None`
- Collections: `list`, `dict`
- UUIDs: Stored as strings, deserialized via type hints
- Domain models: Stored by subscription_id, loaded via type hints
- Dates: Stored as ISO strings

### Critical Rule: Return Domain Models

Domain model changes are only persisted if the model is returned in the state dict:

```python
# WRONG — changes are silently lost
@step("Update")
def update(subscription: MyModel) -> State:
    subscription.port_block.speed = 1000
    return {"speed_updated": True}

# CORRECT — model returned, changes persisted
@step("Update")
def update(subscription: MyModel) -> State:
    subscription.port_block.speed = 1000
    return {"subscription": subscription}
```
