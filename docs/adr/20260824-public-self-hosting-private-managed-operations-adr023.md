<!-- SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0 -->

# ADR-023: Public Self-Hosting vs Private Managed Operations Boundary

**Status:** Accepted
**Date:** 2026-08-24
**Decision authority:** SecPal maintainers

**Decision provenance:** This ADR records architecture decisions deliberately
adopted during the August 2026 rebaseline. 2026-08-24 is the durable ADR record
date, not an assertion that this PR first made those decisions. The 2026-08-28
refinement under [#748](https://github.com/SecPal/.github/issues/748) clarifies
the original public/private ownership boundary; it is not a new architecture
decision or a replacement ADR.

## Context

Public self-hosting must remain secure and recoverable without depending on
SecPal Managed customer, fleet, commercial, or policy knowledge. The original
boundary was too broad: it could be read as making every provider integration,
monitoring component, or capacity concern private merely because SecPal Managed
might use it. Provider API integration is not itself confidential and is not an
architecture ownership boundary.

## Binding decision

### Public portable capability

Public `SecPal/deployment` and the other public SecPal repositories own every
portable contract required for an independent operator to understand, install,
provision, secure, operate, update, monitor, notify, recover, verify, and qualify
SecPal correctly. A provider-specific implementation is public when it
implements a portable technical capability without embedding SecPal Managed
customer, fleet, placement, commercial, or policy knowledge.

Public capability may therefore include:

- provider-neutral provisioning interfaces and bounded infrastructure `Create`,
  `Inspect`, `Rebuild`, and `Delete` primitives;
- reviewed adapters for concrete infrastructure providers, infrastructure
  bootstrap inputs, host admission and conformance, ephemeral qualification
  infrastructure, and provider-specific qualification evidence;
- generic public-network-identity and endpoint-switch interfaces, including
  independently useful DNS, L4, floating-address, or reserved-address adapter
  seams;
- generic health and degradation evidence; runtime, security, update, version,
  and end-of-life detection; configurable notification interfaces; host
  hardening prerequisites; and socketless or otherwise least-authority runtime
  detection capabilities;
- provider-neutral compute, capacity, and resource-quality definitions.

Public capability is not a commitment to support every provider or product. A
public adapter remains bounded by its reviewed contract and qualification
evidence. It must not contain customer or fleet inventory, commercial placement
policy, provider account/payment credentials, or mutable confidential production
state.

### Provider products and durable capacity concepts

Concrete provider products are not SecPal architecture primitives. Durable
architecture may distinguish a capacity profile, compute isolation class such
as `shared`, `dedicated-vcpu`, or `dedicated-host`, CPU architecture such as
`amd64` or `arm64`, storage/performance capability, and ADR-022's `single`,
`replacement`, or `ha` topology.

Hetzner CX/CPX/CAX/CCX or bare-metal models, AWS EC2 instance types,
DigitalOcean Droplet types, GCP machine types, and future equivalents may appear
as reproducible qualification evidence, current provider-catalog mappings, or
private placement/procurement data. They do not define SecPal capacity semantics
and their presence in public qualification evidence does not make private
placement policy public.

### Private SecPal Managed orchestration and policy

Private `SecPal/operations` owns the SecPal Managed-specific orchestration,
policy, customer/fleet knowledge, and commercial operating delta:

- customer, deployment, and environment inventory, including mapping a customer
  to a deployment, provider, region, and host;
- fleet desired-versus-observed state, provider placement and current SKU
  selection policy, procurement policy, customer/workload sizing decisions,
  capacity/scaling policy, and cost, margin, reserve, and commercial capacity
  decisions;
- rollout, canary, and wave policy; maintenance windows; managed Blue/Green,
  `single`-to-`ha`, DNS/customer-domain lifecycle, and automatic remediation
  orchestration;
- fleet-wide aggregation, customer-specific monitoring policy, alert routing,
  paging, escalation, service-level commitments, on-call/SOC workflows,
  remediation authorization, customer lifecycle, and commercial operating
  procedures.

This ownership describes the responsible managed systems and policies; it does
not authorize storing their confidential values in Git. Customer/fleet inventory
and mutable desired/observed state belong in separately authorized operational
systems.

Private operations consumes the public technical contracts. It must not create
a second secret definition of what is conformant, healthy, supported,
vulnerable, or technically safe. Provider-specific code does not move into
`SecPal/operations` merely because Managed Operations invokes it; the private
boundary begins where customer/fleet knowledge, commercial choice, or managed
policy is added.

### Detection and production mutation authority

Scanners, detectors, and health/update components emit bounded facts, evidence,
and findings. Detection alone grants no production mutation authority, and such
components must not hold mutation credentials merely because they can identify
a problem. This preserves ADR-021's separation between scanner evidence and
central policy, including its prohibition on findings automatically rebuilding
or deploying production.

A separately authorized SecPal Managed policy/workflow may consume the public
findings and, after its own customer/fleet policy, authorization, and safety
gates, trigger rollout, Blue/Green replacement, update, or remediation. This is
explicit managed automation, not implicit detector-driven mutation: the finding
is evidence input, never the authority or decision to mutate. Public self-host
operators may likewise act through the reviewed public operational contracts
without depending on the private policy engine.

### Never in Git

`Never in Git` overrides every public/private classification. Neither public nor
private Git may contain production credentials, provider account/payment
credentials, API tokens, passwords, private keys, backup-decryption authority,
production notification/webhook secrets, customer data, customer-confidential
inventory, mutable live infrastructure state, or other secret runtime values.
Private Git is not a secret store.

## Consequences and boundaries

Independent operators receive complete portable technical capability rather
than a deliberately incomplete public implementation. SecPal Managed composes
those public contracts with private orchestration and policy instead of becoming
a hidden technical dependency or maintaining divergent conformance rules.

This ADR defines the ownership boundary; it does not claim that
`SecPal/operations` is currently an executable, privileged production operations
control plane. Under [#705](https://github.com/SecPal/.github/issues/705), that
repository is currently information/architecture collection. Before it gains
executable or privileged production automation or live control-plane
responsibility, a separate governance/security-hardening contract must be
accepted. This refinement does not bypass that requirement.

## Relationships

Codifies [#695](https://github.com/SecPal/.github/issues/695) and is refined by
[#748](https://github.com/SecPal/.github/issues/748). ADR-018 owns the host and
container-runtime baseline, ADR-019 owns the public edge and layered-security
decision, ADR-021 owns OCI supply-chain evidence and scanner-policy semantics,
and ADR-022 owns the topology vocabulary and guarantees. This ADR owns only the
public/private capability and policy boundary; endpoint mechanisms do not alter
ADR-022 topology semantics. See also
[#705](https://github.com/SecPal/.github/issues/705) and ADR-020.
