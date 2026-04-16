# YAML Configuration File Reference

Complete reference for the YAML product configuration file used by `python main.py generate` commands.

## Table of Contents

- [Full Example](#full-example)
- [Root-Level Fields](#root-level-fields)
- [Global Config Section](#global-config-section)
- [Fixed Inputs](#fixed-inputs)
- [Product Blocks](#product-blocks)
- [Product Block Fields](#product-block-fields)
- [Field Types](#field-types)
- [Lifecycle Requirements](#lifecycle-requirements)
- [Validations](#validations)
- [Workflows Section](#workflows-section)

## Full Example

```yaml
config:
  summary_forms: true

name: node
type: Node
tag: NODE
description: "Network node"

fixed_inputs:
  - name: node_rack_mountable
    type: bool
    description: "is node rack mountable"
  - name: node_vendor
    type: enum
    description: "vendor of node"
    enum_type: str
    values:
      - "Cisco"
      - "Nokia"

product_blocks:
  - name: node
    type: Node
    tag: NODE
    description: "node product block"
    fields:
      - name: node_name
        description: "Unique name of the node"
        type: str
        required: provisioning
        modifiable:
      - name: node_description
        description: "Description of the node"
        type: str
        modifiable:
      - name: ims_id
        description: "ID in inventory management system"
        type: int
        required: active
      - name: under_maintenance
        description: "node is under maintenance"
        type: bool
        required: initial
        default: False

workflows:
  - name: terminate
    validations:
      - id: can_only_terminate_when_under_maintenance
        description: "Can only terminate when the node is placed under maintenance"
  - name: validate
    enabled: false
    validations:
      - id: validate_ims_administration
        description: "Validate that the node is correctly administered in IMS"
```

## Root-Level Fields

```yaml
name: service_port          # Product name in snake_case (REQUIRED)
                            # Used for variable names, filenames, descriptions
type: ServicePort           # Product type in PascalCase (REQUIRED)
                            # Used in Python class names and database
tag: SP                     # Product tag, typically uppercase (REQUIRED)
                            # Used for database registration and filtering
description: "Description"  # Descriptive text (REQUIRED)
variable: my_var            # Override derived variable name (OPTIONAL)
                            # Defaults to camel_to_snake(name)
```

## Global Config Section

```yaml
config:
  summary_forms: true       # Generate summary forms in create/modify workflows
                            # Default: false
```

When `summary_forms` is true, the generated create and modify workflows include a read-only summary page before submission.

## Fixed Inputs

Fixed inputs are static values selected at product creation time. They create distinct product variants in the database.

```yaml
fixed_inputs:
  - name: field_name        # Field name (REQUIRED)
    type: str|int|bool|enum # Field type (REQUIRED)
    description: "text"     # Description (REQUIRED)
    default: value          # Default value (OPTIONAL)

    # Required only for enum type:
    enum_type: str|int      # Enum value type
    values:                 # List of possible values
      - "value1"
      - "value2"
```

### Enum Fixed Inputs and Product Variants

When enum fixed inputs are specified, the migration generates **all combinations** as separate products:

```yaml
fixed_inputs:
  - name: vendor
    type: enum
    enum_type: str
    values: ["Cisco", "Nokia"]
  - name: ports
    type: enum
    enum_type: int
    values: [10, 20, 40]
```

This creates 6 product variants: "Cisco 10", "Cisco 20", "Cisco 40", "Nokia 10", "Nokia 20", "Nokia 40".

## Product Blocks

Product blocks are domain model building blocks containing fields (resource types).

**Rule**: Exactly 1 product block must be the root — not referenced by any other block. The generator raises an error if this constraint is violated.

```yaml
product_blocks:
  - name: block_name        # Block name in snake_case (REQUIRED)
    type: BlockType         # Block type in PascalCase (REQUIRED)
    tag: BT                 # Block tag, typically uppercase (REQUIRED)
    description: "text"     # Block description (REQUIRED)
    variable: my_block      # Override variable name (OPTIONAL)
    fields: [...]           # List of resource type fields (REQUIRED)
```

### Nested Product Blocks

Blocks can reference other blocks. The generator resolves dependencies via topological sort:

```yaml
product_blocks:
  - name: port
    type: Port
    tag: PORT
    description: "physical port"
    fields:
      - name: port_name
        type: str
        required: provisioning

  - name: service
    type: Service
    tag: SVC
    description: "service using ports"
    fields:
      - name: service_name
        type: str
        required: provisioning
      - name: ports
        type: list
        list_type: Port          # References the Port block above
        min_items: 1
        max_items: 4
```

Here `Service` is the root block (not referenced by others).

## Product Block Fields

```yaml
fields:
  - name: field_name          # Field name in snake_case (REQUIRED)
    type: <type>              # Field type (REQUIRED, see Field Types below)
    description: "text"       # Field description (REQUIRED)
    required: initial|provisioning|active  # When field becomes required (OPTIONAL)
    modifiable:               # Allow modification via modify workflow (OPTIONAL)
    default: value            # Default value (OPTIONAL, REQUIRED when required=initial)

    # For constrained integers:
    min_value: 1              # Minimum value (OPTIONAL)
    max_value: 32767          # Maximum value (OPTIONAL)

    # For list types:
    list_type: TypeName       # Item type (REQUIRED for type=list)
    min_items: 1              # Minimum list length (OPTIONAL)
    max_items: 10             # Maximum list length (OPTIONAL)

    # For enum types:
    enum_type: str|int        # Enum value type (REQUIRED for type=enum)
    values: [...]             # Possible values (REQUIRED for type=enum)

    validations: [...]        # Field validations (OPTIONAL)
```

## Field Types

| Type | Description | Extra Fields |
|------|-------------|-------------|
| `str` | String | — |
| `int` | Integer | `min_value`, `max_value` for constraints |
| `bool` | Boolean | — |
| `enum` | Enumeration | `enum_type` (str/int), `values` |
| `list` | List with constraints | `list_type`, `min_items`, `max_items` |
| `ipaddress.IPv4Address` | Namespaced import type | — |
| `ExistingBlock` | Existing product block | Uses block type name (e.g. `UserGroup`) |

### Examples

```yaml
# Simple string
- name: description
  type: str
  description: "Service description"

# Constrained integer (generates Annotated[int, Ge(1), Le(32767)])
- name: ims_id
  type: int
  min_value: 1
  max_value: 32767
  description: "IMS inventory ID"

# Namespaced type (generates import statement)
- name: ipv4_loopback
  type: ipaddress.IPv4Address
  description: "IPv4 loopback address"

# Reference to existing product block
- name: user_group
  type: UserGroup
  description: "User group assignment"

# List of product blocks with size constraints
- name: link_members
  type: list
  list_type: Link
  min_items: 2
  max_items: 2
  description: "Circuit link members"

# Enum field
- name: port_mode
  type: enum
  enum_type: str
  values: ["untagged", "tagged", "link_member"]
  default: "tagged"
  description: "Port VLAN mode"
```

## Lifecycle Requirements

The `required` field controls when a field becomes mandatory across subscription lifecycle stages:

```
INITIAL → PROVISIONING → ACTIVE
```

| `required` Value | INITIAL | PROVISIONING | ACTIVE |
|-----------------|---------|--------------|--------|
| `initial` | Required | Required | Required |
| `provisioning` | Optional (`None`) | Required | Required |
| `active` | Optional (`None`) | Optional (`None`) | Required |
| _(omitted)_ | Optional (`None`) | Optional (`None`) | Optional (`None`) |

**Rules**:
- When `required: initial`, a `default` value is mandatory
- The generated domain model classes enforce these constraints via type annotations
- `Type | None = None` for optional stages, `Type` for required stages

## Validations

Validations generate skeleton validator functions for use in forms and workflows.

### Field-Level Validations

```yaml
fields:
  - name: port_mode
    type: enum
    enum_type: str
    values: ["untagged", "tagged"]
    validations:
      - id: must_be_unused_to_change_mode
        description: "Mode can only be changed when no services are attached"
```

Generates:
- An `AfterValidator` annotated type in `shared/forms.py`
- A skeleton validator function to implement

### Workflow-Level Validations

```yaml
workflows:
  - name: create
    validations:
      - id: endpoints_cannot_be_on_same_node
        description: "Service endpoints must land on different nodes"
```

Generates:
- A `model_validator` in the create workflow's input form
- A validation step in the validate workflow

## Workflows Section

```yaml
workflows:
  - name: create|modify|terminate|validate  # Workflow type (REQUIRED)
    enabled: true|false                     # Generate code? (DEFAULT: true)
    validations:                            # Workflow validations (OPTIONAL)
      - id: validation_function_name
        description: "Human-readable description"
```

When a workflow type is omitted entirely, default scaffolding is generated. Set `enabled: false` to skip generation for that type.
