# Domain Models — Complete Reference

## Overview

Domain models are Python classes that represent subscriptions and their components. They enforce field requirements at each lifecycle stage and serialize to/from the database.

Two base classes:
- **`ProductBlockModel`** — Building block containing resource type fields
- **`SubscriptionModel`** — Top-level subscription containing product blocks

## ProductBlockModel

Define three lifecycle variants (Inactive, Provisioning, Active) with increasingly strict field requirements:

```python
from orchestrator.domain.base import ProductBlockModel
from orchestrator.types import SubscriptionLifecycle

# Inactive = INITIAL + TERMINATED (least strict)
class PortBlockInactive(ProductBlockModel, product_block_name="Port"):
    port_name: str | None = None
    port_speed: int | None = None
    external_id: str | None = None

# Provisioning (medium strict)
class PortBlockProvisioning(
    PortBlockInactive,
    lifecycle=[SubscriptionLifecycle.PROVISIONING],
):
    port_name: str                  # Now required
    port_speed: int | None = None   # Still optional

    @computed_field
    @property
    def title(self) -> str:
        return f"Port {self.port_name}"

# Active (most strict)
class PortBlock(
    PortBlockProvisioning,
    lifecycle=[SubscriptionLifecycle.ACTIVE],
):
    port_name: str
    port_speed: int                 # Now required
    external_id: str                # Now required
```

### Lifecycle Stage Rules

| Stage | When | Validation |
|-------|------|-----------|
| **Inactive** | INITIAL + TERMINATED | Minimal — most fields optional |
| **Provisioning** | PROVISIONING | Medium — core identity fields required |
| **Active** | ACTIVE | Strict — all operational fields required |

### Field Requirement Pattern

```python
# Always optional
field: str | None = None

# Required from INITIAL (must have default in config)
field: str = "default_value"

# Required from PROVISIONING
# Inactive: str | None = None
# Provisioning: str
# Active: str

# Required from ACTIVE
# Inactive: str | None = None
# Provisioning: str | None = None
# Active: str
```

## SubscriptionModel

Top-level model wrapping product blocks. Same three-variant pattern:

```python
from orchestrator.domain.base import SubscriptionModel

class ServicePortInactive(SubscriptionModel, is_base=True):
    port: PortBlockInactive

class ServicePortProvisioning(
    ServicePortInactive,
    lifecycle=[SubscriptionLifecycle.PROVISIONING],
):
    port: PortBlockProvisioning

class ServicePort(
    ServicePortProvisioning,
    lifecycle=[SubscriptionLifecycle.ACTIVE],
):
    port: PortBlock
```

Note `is_base=True` on the Inactive variant — this marks it as the base class for the subscription model hierarchy.

## Nested Product Blocks

Product blocks can contain other product blocks:

```python
class LinkBlockInactive(ProductBlockModel, product_block_name="Link"):
    link_id: int | None = None

class CircuitBlockInactive(ProductBlockModel, product_block_name="Circuit"):
    circuit_name: str | None = None
    links: list[LinkBlockInactive] = []

class CircuitBlockProvisioning(
    CircuitBlockInactive,
    lifecycle=[SubscriptionLifecycle.PROVISIONING],
):
    circuit_name: str
    links: list[LinkBlockProvisioning]  # Nested blocks follow lifecycle too
```

## Lifecycle Transitions

### `from_other_lifecycle` — Change Lifecycle Stage

Transition a domain model from one lifecycle stage to another:

```python
@step("Activate subscription")
def activate(subscription: ServicePortProvisioning) -> State:
    # Transition from Provisioning → Active
    active_subscription = ServicePort.from_other_lifecycle(
        subscription,
        SubscriptionLifecycle.ACTIVE,
    )
    return {"subscription": active_subscription}
```

This validates that all required fields for the target lifecycle are present. Raises `ValidationError` if requirements are not met.

### Common Transition Patterns

**Create workflow**: Inactive → Provisioning → Active

```python
@step("Construct model")
def construct(product: UUID, customer_id: str, port_name: str) -> State:
    # Start in INITIAL (Inactive)
    subscription = ServicePortInactive.from_product_id(product, customer_id)
    subscription.port = PortBlockInactive.new(subscription_id=subscription.subscription_id)
    subscription.port.port_name = port_name
    return {"subscription": subscription}

@step("Set to provisioning")
def set_provisioning(subscription: ServicePortInactive) -> State:
    subscription = ServicePortProvisioning.from_other_lifecycle(subscription)
    return {"subscription": subscription}

@step("Activate")
def activate(subscription: ServicePortProvisioning) -> State:
    subscription = ServicePort.from_other_lifecycle(subscription)
    return {"subscription": subscription}
```

**Modify workflow**: Active → Provisioning → Active

```python
@step("Start modification")
def start_modify(subscription: ServicePort) -> State:
    # Downgrade to Provisioning for modification
    subscription = ServicePortProvisioning.from_other_lifecycle(subscription)
    return {"subscription": subscription}

@step("Apply changes and reactivate")
def apply_and_activate(subscription: ServicePortProvisioning, new_speed: int) -> State:
    subscription.port.port_speed = new_speed
    subscription = ServicePort.from_other_lifecycle(subscription)
    return {"subscription": subscription}
```

## Loading from Database

### `from_subscription` — Load by ID

```python
subscription = ServicePort.from_subscription(subscription_id)
```

Loads the subscription from the database and reconstructs the full domain model hierarchy. The lifecycle variant must match the subscription's current status.

### Automatic Loading via State Injection

When a step declares a domain model parameter, the orchestrator loads it automatically:

```python
@step("Process")
def process(subscription: ServicePort) -> State:
    # subscription loaded from DB via state["subscription"] UUID
    return {"subscription": subscription}
```

### `from_product_id` — Create New

```python
subscription = ServicePortInactive.from_product_id(
    product_id=product_uuid,
    customer_id=customer_id,
)
```

Creates a new subscription instance (not yet persisted).

## Computed Fields

Add computed properties using Pydantic's `@computed_field`:

```python
from pydantic import computed_field

class PortBlockProvisioning(PortBlockInactive, ...):
    port_name: str
    port_speed: int | None = None

    @computed_field
    @property
    def title(self) -> str:
        return f"Port {self.port_name}"

    @computed_field
    @property
    def description(self) -> str:
        speed = f" ({self.port_speed}G)" if self.port_speed else ""
        return f"{self.port_name}{speed}"
```

The `title` computed field is commonly used for display in the frontend.

## Subscription Description

The subscription `description` field is auto-generated from the product name, fixed inputs, and block titles. Override by implementing `generate_description()` on the Provisioning variant:

```python
class ServicePortProvisioning(ServicePortInactive, ...):
    port: PortBlockProvisioning

    def generate_description(self) -> str:
        return f"Service Port {self.port.port_name}"
```

## Sync State

Subscriptions have an `insync` flag:
- `True` — Available for workflows
- `False` — Locked by a running workflow

The `unsync` and `resync` built-in steps manage this flag. Workflow decorators handle this automatically.

## Common Patterns

### Creating a New Subscription in a Create Workflow

```python
@step("Construct subscription model")
def construct_model(
    product: UUID,
    customer_id: str,
    port_name: str,
    port_speed: int,
) -> State:
    subscription = ServicePortInactive.from_product_id(product, customer_id)
    subscription.port = PortBlockInactive.new(
        subscription_id=subscription.subscription_id,
    )
    subscription.port.port_name = port_name
    subscription.description = f"Port {port_name}"
    return {
        "subscription": subscription,
        "subscription_id": subscription.subscription_id,
        "subscription_description": subscription.description,
    }
```

### Updating Fields in a Modify Workflow

```python
@step("Update subscription")
def update_subscription(
    subscription: ServicePort,
    new_description: str,
    new_speed: int,
) -> State:
    # Downgrade to provisioning for modification
    subscription = ServicePortProvisioning.from_other_lifecycle(subscription)
    subscription.port.port_speed = new_speed
    subscription.description = new_description
    # Upgrade back to active
    subscription = ServicePort.from_other_lifecycle(subscription)
    return {"subscription": subscription}
```

### Validating Against External Systems

```python
@step("Validate external state")
def validate_external(subscription: ServicePort) -> State:
    external_state = network_api.get_port(subscription.port.external_id)

    if external_state["speed"] != subscription.port.port_speed:
        raise ValueError(
            f"Speed mismatch: DB={subscription.port.port_speed}, "
            f"external={external_state['speed']}"
        )
    return {}
```
