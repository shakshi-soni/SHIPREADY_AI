# Tests

This directory contains the automated test suite for the target project.

The tests are designed to verify the application's expected behavior and provide objective evidence that the project is functioning correctly.

## Test Suite

The test suite currently covers:

* Health endpoint behavior
* Initial task list state
* Successful task creation
* Validation of missing task titles
* Task persistence within the application
* Task listing behavior

## Test Coverage

### Health Check

Verifies that:

```text id="m9q0xk"
GET /health
```

returns HTTP `200` and reports:

```json
{
  "status": "healthy"
}
```

### Task Listing

Verifies that a newly initialized application returns an empty task list.

### Task Creation

Verifies that a valid task can be created through:

```text id="kq2b3m"
POST /tasks
```

and that the returned task contains the expected:

* `id`
* `title`
* `done`

values.

### Input Validation

Verifies that attempting to create a task without a title returns HTTP `400` and an appropriate error response.

### Task Retrieval

Verifies that tasks created through the API can subsequently be retrieved from:

```text id="8xv1hd"
GET /tasks
```

and appear in the expected order.

## Running the Tests

From the target project directory, run:

```bash
pytest
```

For more detailed output:

```bash
pytest -v
```

## Test Isolation

The test suite resets the shared task state before each test so that individual tests remain independent of one another.

The Flask test client is used to exercise the application without requiring a separate production server.

## ShipReady Verification

This test suite is intentionally part of ShipReady's verification workflow.

ShipReady treats the tests as **read-only** and does not modify them during the repair process.

The agent may modify the target application's implementation to satisfy the existing requirements, but the expected behavior defined by the tests remains unchanged.

The verification flow therefore becomes:

```text
Inspect project
      ↓
Read readiness contract
      ↓
Inspect test suite
      ↓
Identify implementation gaps
      ↓
Repair target application
      ↓
Run existing tests
      ↓
Verify results independently
      ↓
Record evidence
```

A successful test run provides concrete evidence that the target application's required behavior is working as expected.

## Purpose

The purpose of this directory is not to allow the agent to rewrite tests until they pass.

Instead, the tests define the expected behavior that the implementation must satisfy.

**The implementation changes. The verification standard does not.**
