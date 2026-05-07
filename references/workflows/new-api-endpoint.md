# Workflow: New API Endpoint

## When to use
Adding a new REST/GraphQL endpoint that may affect multiple repos (backend implementation + frontend consumption + spec update).

## Steps

1. **Check spec**: Read the relevant spec in specs repo. If endpoint is already specified, proceed to step 3. If not, go to step 2.

2. **Propose spec change**: Run `/otaman:propose` with the endpoint details (method, path, request/response schema). **STOP** and add to blocked queue until approved.

3. **Implement backend**: In the owning backend repo:
   - Create route/controller
   - Add request validation
   - Implement business logic
   - Write unit tests
   - Add OpenAPI decorator/doc

4. **Send contract-change**: Use `otaman_send` to notify frontend/consuming agents:
   - Include: method, path, request/response types, any breaking changes
   - Priority: `high` if breaking, `normal` otherwise

5. **Implement consumers**: Frontend/mobile agents pick up the contract-change and update their API clients.

6. **Integration test**: Both sides verify the contract matches.

## Bus messages generated
- `spec-change-request` (if spec didn't exist)
- `contract-change` (after implementation)
- `task-assignment` (to consuming repos)
