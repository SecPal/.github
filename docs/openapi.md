<!--
SPDX-FileCopyrightText: 2025 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# OpenAPI Conventions

> **Single Source of Truth:** `docs/openapi.yaml` defines the API contract. Backend and frontend must conform.

## Overview

This document outlines the OpenAPI conventions and standards used across SecPal projects. All API changes must follow these guidelines to ensure consistency, maintainability, and compatibility.

## File Location

- **Specification:** `docs/openapi.yaml` or `contracts/openapi.yaml`
- **Format:** OpenAPI 3.1
- **Validation:** Spectral CLI

## Naming Conventions

### Endpoints

- Use **kebab-case** for path segments: `/api/v1/guard-reports`
- Use **plural nouns** for collections: `/users`, `/shifts`
- Use **singular for actions**: `/users/{id}/activate`

### Schema Names

- Use **PascalCase**: `GuardReport`, `UserProfile`
- Suffix error schemas with `Error`: `ValidationError`
- Suffix request bodies with `Request`: `CreateUserRequest`
- Suffix responses with `Response`: `UserListResponse`

### Properties

- Use **camelCase** for property names: `firstName`, `createdAt`
- Use **snake_case** only for legacy compatibility if required

## Structure Guidelines

### Versioning

- **URI versioning:** `/api/v1/...`, `/api/v2/...`
- Maintain backward compatibility within major versions
- Document breaking changes in changelog

### Request Bodies

```yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        $ref: "#/components/schemas/CreateUserRequest"
      examples:
        default:
          $ref: "#/components/examples/CreateUserExample"
```

### Response Structure

**Success responses:**

```yaml
responses:
  "200":
    description: Successful operation
    content:
      application/json:
        schema:
          $ref: "#/components/schemas/UserResponse"
  "201":
    description: Resource created
    headers:
      Location:
        schema:
          type: string
        description: URI of created resource
```

**Error responses (RFC 7807):**

```yaml
responses:
  "400":
    description: Bad Request
    content:
      application/problem+json:
        schema:
          $ref: "#/components/schemas/ProblemDetails"
```

## Error Responses

Use **RFC 7807 Problem Details** format (`application/problem+json`):

```json
{
  "type": "https://api.secpal.example/errors/validation-error",
  "title": "Validation Failed",
  "status": 400,
  "detail": "The request body contains invalid data",
  "instance": "/api/v1/users",
  "errors": [
    {
      "field": "email",
      "message": "Invalid email format"
    }
  ]
}
```

### Standard Error Schema

```yaml
components:
  schemas:
    ProblemDetails:
      type: object
      required:
        - type
        - title
        - status
      properties:
        type:
          type: string
          format: uri
          description: URI reference identifying the problem type
        title:
          type: string
          description: Short, human-readable summary
        status:
          type: integer
          description: HTTP status code
        detail:
          type: string
          description: Human-readable explanation
        instance:
          type: string
          format: uri
          description: URI reference identifying specific occurrence
```

## Pagination

Use **cursor-based pagination** for consistent, performant results:

### Request Parameters

```yaml
parameters:
  - name: cursor
    in: query
    schema:
      type: string
    description: Pagination cursor from previous response
  - name: limit
    in: query
    schema:
      type: integer
      minimum: 1
      maximum: 100
      default: 20
    description: Number of items to return
```

### Pagination Response Format

```yaml
components:
  schemas:
    PaginatedResponse:
      type: object
      required:
        - data
        - meta
      properties:
        data:
          type: array
          items: {}
        meta:
          type: object
          required:
            - has_more
          properties:
            next_cursor:
              type: string
              nullable: true
              description: Cursor for next page (null if no more pages)
            has_more:
              type: boolean
              description: Whether more results are available
            total:
              type: integer
              description: Total count (optional, expensive to compute)
```

## Authentication

### OAuth2 Bearer Tokens

```yaml
components:
  securitySchemes:
    BearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
      description: JWT access token

security:
  - BearerAuth: []
```

### Security Considerations

- All authenticated endpoints must have `security` declaration
- Document required scopes/permissions
- Use HTTPS only (enforce in production)

## Caching

### ETag Support

```yaml
responses:
  "200":
    description: Successful response
    headers:
      ETag:
        schema:
          type: string
        description: Entity tag for cache validation
    content:
      application/json:
        schema:
          $ref: "#/components/schemas/Resource"
  "304":
    description: Not Modified (resource unchanged)
```

### Request Headers

```yaml
parameters:
  - name: If-None-Match
    in: header
    schema:
      type: string
    description: ETag from previous response
```

## Rate Limiting

### Response Headers

```yaml
responses:
  "200":
    headers:
      X-RateLimit-Limit:
        schema:
          type: integer
        description: Request limit per window
      X-RateLimit-Remaining:
        schema:
          type: integer
        description: Remaining requests in current window
      X-RateLimit-Reset:
        schema:
          type: integer
          format: int64
        description: Unix timestamp when limit resets
```

### Rate Limit Exceeded

```yaml
"429":
  description: Too Many Requests
  headers:
    Retry-After:
      schema:
        type: integer
      description: Seconds to wait before retrying
  content:
    application/problem+json:
      schema:
        $ref: "#/components/schemas/ProblemDetails"
```

## Validation Requirements

### Pre-commit Checks

All OpenAPI changes must pass:

```bash
# Lint with Spectral
npx @stoplight/spectral-cli lint docs/openapi.yaml

# Validate structure
npx @redocly/cli lint docs/openapi.yaml
```

### Spectral Rulesets

Use standard rulesets with custom rules:

- **Operation IDs:** Must be unique and descriptive
- **Examples:** Required for all request/response schemas
- **Descriptions:** Required for all operations, parameters, schemas
- **Security:** All operations must declare security requirements
- **Deprecation:** Deprecated operations must include `x-sunset` extension

### Breaking Changes

Changes that require major version bump:

- ❌ Removing endpoints
- ❌ Removing required properties
- ❌ Changing property types
- ❌ Adding required parameters
- ✅ Adding optional parameters (backward compatible)
- ✅ Adding new endpoints (backward compatible)
- ✅ Adding optional properties (backward compatible)

## Documentation

### Operation Descriptions

```yaml
paths:
  /users:
    post:
      summary: Create a new user
      description: |
        Creates a new user account with the provided details.

        **Requirements:**
        - Email must be unique
        - Password must meet complexity requirements

        **Side Effects:**
        - Sends welcome email to user
        - Creates default preferences
      operationId: createUser
```

### Examples

Provide realistic examples for all schemas:

```yaml
components:
  examples:
    CreateUserExample:
      summary: Create new user
      value:
        email: user@example.com
        firstName: John
        lastName: Doe
        password: "SecureP@ssw0rd"
```

## Status Code Guidelines

Use appropriate HTTP status codes:

- **200 OK:** Successful GET, PUT, PATCH, DELETE
- **201 Created:** Successful POST (new resource)
- **204 No Content:** Successful DELETE (no body)
- **400 Bad Request:** Invalid request body/parameters
- **401 Unauthorized:** Missing/invalid authentication
- **403 Forbidden:** Authenticated but insufficient permissions
- **404 Not Found:** Resource does not exist
- **409 Conflict:** Resource conflict (duplicate, version mismatch)
- **422 Unprocessable Entity:** Validation failed
- **429 Too Many Requests:** Rate limit exceeded
- **500 Internal Server Error:** Unexpected server error

## References

- [OpenAPI Specification 3.1](https://spec.openapis.org/oas/v3.1.0)
- [RFC 7807 Problem Details](https://www.rfc-editor.org/rfc/rfc7807)
- [Spectral Documentation](https://stoplight.io/open-source/spectral)
- [API Design Guidelines (Microsoft)](https://github.com/microsoft/api-guidelines)
