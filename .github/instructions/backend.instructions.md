<!--
SPDX-FileCopyrightText: 2025 SecPal
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Backend Instructions (Laravel/PHP)

> **Note:** These instructions are organization-level defaults from `SecPal/.github`.
> Copy to `SecPal/backend/.github/copilot-instructions.md` when backend repo is created.

**Applies to:** `app/**`, `routes/**`, `database/**`, `tests/**`, `docs/openapi.yaml`

## Path-Scoped Rules (Preflight Integration)

<!--
These rules can be activated for local preflight checks in backend repo:

applyTo:
  - "app/**"
  - "docs/openapi.yaml"

rules:
  - "Eloquent: eager loading verpflichtend; keine N+1."
  - "Validierung via FormRequests; API-Output via Resources/DTO."
  - "Migrations mit Rollback-Plan dokumentieren."
-->

## Architecture

- Follow Laravel conventions (Service → Repository → Model)
- Keep controllers thin (delegate to services)
- Use form requests for validation
- Leverage Laravel's dependency injection

## Code Style

```bash
# Always run before committing
./vendor/bin/pint --test
```

**Rules:**

- PSR-12 compliant (enforced by Pint)
- Type hints everywhere (strict_types=1)
- Return types on all methods
- No `@var` tags if type can be inferred

## Testing

```bash
# Run tests in parallel
php artisan test --parallel

# Single test
php artisan test --filter=UserControllerTest
```

**Requirements:**

- Unit tests for services/repositories
- Feature tests for API endpoints
- Test factories for all models
- Pest syntax (preferred over PHPUnit)

## Static Analysis

```bash
./vendor/bin/phpstan analyse --level=max
```

**Common fixes:**

- Add type hints to resolve unknowns
- Document array shapes with `@param`
- Use generics for collections

## Database

- All schema changes via migrations
- Use factories for seeders
- Soft deletes for user data
- UUID primary keys (consider for scale)

## API Responses

Match OpenAPI spec exactly:

```php
return response()->json([
    'data' => $resource,
    'meta' => [
        'cursor' => $nextCursor,
    ],
], 200);
```

## Error Handling

Use `application/problem+json`:

```php
throw new HttpException(400, 'Validation failed', [
    'type' => 'https://example.com/problems/validation',
    'title' => 'Validation Error',
    'detail' => 'Email is required',
    'instance' => '/users',
]);
```

## Security

- Validate all input (FormRequest classes)
- Authorize all actions (Policies)
- Rate limit API endpoints
- No raw SQL (use query builder)
- Hash passwords (bcrypt)

## Performance

- Eager load relationships (avoid N+1)
- Cache expensive queries
- Use queues for async work
- Index foreign keys

## Resources

- [Laravel Docs](https://laravel.com/docs)
- [Pest Docs](https://pestphp.com)
- [PHPStan Rules](https://phpstan.org/rules)
