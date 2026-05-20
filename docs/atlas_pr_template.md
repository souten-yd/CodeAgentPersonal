# Atlas PR Template

## PR Name

...

## Purpose

...

## Scope

In scope:
- ...

Out of scope:
- ...

## Preflight Confirmation

- [ ] Read handoff
- [ ] Read roadmap
- [ ] Read constitution
- [ ] Confirmed latest merged PR
- [ ] Inspected actual main files
- [ ] Verified related tests
- [ ] Verified helper/API/UI wiring

## Safety Confirmation

- [ ] no shell=True
- [ ] no remote git
- [ ] no execute all
- [ ] no auto continue
- [ ] no automatic safe_apply
- [ ] no automatic verification
- [ ] no automatic patch generation
- [ ] no automatic test execution
- [ ] no Path("ca_data") direct writes
- [ ] classic script contract preserved

## Implementation Summary

...

## Tests

...

## Runtime Chain Evidence

(Allow “N/A” only with explanation.)

- DOM ID:
- API helper:
- Dashboard binding:
- Endpoint:
- Router registration:
- Service/data_root injection:
- Response unwrap:
- Render target:
- Cache bust:
- Test that fails if binding is missing:
- Test that fails if endpoint is missing:
- Test that fails if response shape is wrong:
- Test that fails if code is outside the IIFE:

## Broken Cases Covered

| Broken case | Test that catches it |
| --- | --- |
| Example: helper missing | test name |
| Example: endpoint missing | test name |
| Example: binding outside IIFE | test name |
| Example: wrong response unwrap | test name |
| Example: data_root not injected | test name |

## Adversarial Self-Review

- At least 5 possible failure modes.
- For each failure mode, list the detecting test.
- If no test catches it, add a test or mark as known limitation.

### UI Example (Recommended)

If adding a button that calls an API, tests must fail when:
- the DOM ID is missing
- the API helper is missing
- the dashboard binding is outside the IIFE
- the response `.data` is not unwrapped
- cache bust is not updated


## Postflight Confirmation

- [ ] targeted pytest passed
- [ ] node --check passed if JS changed
- [ ] grep safety checks reviewed
- [ ] checkpoint docs updated
- [ ] Current PR / Next PR updated

## Known Limitations

...

## Next PR

...
