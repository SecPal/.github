<!--
SPDX-FileCopyrightText: 2025 SecPal
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Development Principles & Best Practices

> **Note:** This is the **human-readable** version of our development principles. The machine-readable source of truth is [`.github/copilot-config.yaml`](../.github/copilot-config.yaml).

This document explains the design principles and best practices that guide all SecPal projects (api, frontend, contracts).

## Quick Navigation

- [Essential Development Principles](#essential-development-principles)
- [SOLID Principles](#solid-principles)
- [Additional Design Principles](#additional-design-principles)
- [Security & Best Practices](#security--best-practices)
- [Framework-Specific Guidelines](#framework-specific-guidelines)

---

## Essential Development Principles

### 1. Quality First

**Principle:** Clean code before quick code, maintainable before feature-complete.

**In Practice:**

- ✅ Write readable, self-documenting code
- ✅ Prefer clarity over cleverness
- ✅ Invest time in proper naming and structure
- ❌ Don't sacrifice quality for speed

**Example:**

```typescript
// ❌ Bad: Quick but unclear
function p(u: User) {
  return u.posts().filter((p) => p.s === "pub");
}

// ✅ Good: Clear and maintainable
function getUserPublishedPosts(user: User): Post[] {
  return user.posts().filter((post) => post.status === "published");
}
```

---

### 2. TDD (Test-Driven Development)

**Principle:** Write the failing test FIRST, then implement the feature.

**Workflow:**

1. 🔴 **Red** - Write a failing test
2. 🟢 **Green** - Write minimal code to pass
3. 🔵 **Refactor** - Improve code while keeping tests green

**Why TDD?**

- ✅ Catches bugs early
- ✅ Documents expected behavior
- ✅ Enables confident refactoring
- ✅ Forces design thinking upfront

---

### 3. DRY (Don't Repeat Yourself)

**Principle:** Every piece of knowledge should have a single, authoritative representation.

**In Practice:**

- ✅ Extract duplicated logic into functions/classes/modules
- ✅ Use shared utilities across repositories
- ✅ Create reusable components
- ❌ Don't copy-paste code

**When to tolerate duplication:**

- 🤔 Two similar-looking pieces that serve different purposes
- 🤔 Premature abstraction would make code harder to understand
- 🤔 Rule of Three: Wait until pattern repeats 3+ times

---

### 4. Clean Before Quick

**Principle:** Refactor existing code when you touch it, even if unrelated to your task.

**In Practice:**

- ✅ Fix poor naming when you encounter it
- ✅ Extract long methods into smaller ones
- ✅ Remove dead code
- ✅ Add type hints if missing
- ❌ Don't leave "broken windows"

---

### 5. Self Review Before Push

**Principle:** Run all quality gates locally before pushing code.

**Checklist:**

```bash
# Run all checks before pushing
./scripts/preflight.sh
```

**Why?**

- ✅ Catches issues before CI (faster feedback)
- ✅ Reduces CI pipeline failures
- ✅ Shows professionalism and care

---

## SOLID Principles

### S - Single Responsibility Principle

**Principle:** A class should have one, and only one, reason to change.

**Example:**

```typescript
// ❌ Bad: Multiple responsibilities
class User {
  saveToDatabase() {
    /* ... */
  }
  sendEmail() {
    /* ... */
  }
  generateReport() {
    /* ... */
  }
}

// ✅ Good: Separate concerns
class User {
  /* ... */
}
class UserRepository {
  saveToDatabase() {
    /* ... */
  }
}
class EmailService {
  sendEmail() {
    /* ... */
  }
}
class ReportGenerator {
  generateReport() {
    /* ... */
  }
}
```

---

### O - Open/Closed Principle

**Principle:** Classes should be open for extension but closed for modification.

**Example:**

```typescript
// ✅ Good: Use interfaces for extension
interface PaymentGateway {
  process(amount: number): Promise<boolean>;
}

class CreditCardGateway implements PaymentGateway {
  async process(amount: number): Promise<boolean> {
    /* ... */
  }
}

class PayPalGateway implements PaymentGateway {
  async process(amount: number): Promise<boolean> {
    /* ... */
  }
}

// Adding new payment type = new class, no modification to existing code
```

---

### L - Liskov Substitution Principle

**Principle:** Subtypes must be substitutable for their base types without breaking functionality.

**Example:**

```typescript
// ✅ Good: Separate interfaces, no inheritance violation
interface Shape {
  getArea(): number;
}

class Rectangle implements Shape {
  constructor(
    private width: number,
    private height: number
  ) {}
  getArea(): number {
    return this.width * this.height;
  }
}

class Square implements Shape {
  constructor(private size: number) {}
  getArea(): number {
    return this.size * this.size;
  }
}
```

---

### I - Interface Segregation Principle

**Principle:** Clients should not be forced to depend on interfaces they don't use.

**Example:**

```typescript
// ❌ Bad: Fat interface
interface Worker {
  work(): void;
  eat(): void;
  sleep(): void;
}

class Robot implements Worker {
  work(): void {
    /* ... */
  }
  eat(): void {
    /* Robots don't eat! */
  }
  sleep(): void {
    /* Robots don't sleep! */
  }
}

// ✅ Good: Segregated interfaces
interface Workable {
  work(): void;
}
interface Feedable {
  eat(): void;
}
interface Sleepable {
  sleep(): void;
}

class Robot implements Workable {
  work(): void {
    /* ... */
  }
}

class Human implements Workable, Feedable, Sleepable {
  work(): void {
    /* ... */
  }
  eat(): void {
    /* ... */
  }
  sleep(): void {
    /* ... */
  }
}
```

---

### D - Dependency Inversion Principle

**Principle:** Depend on abstractions, not concretions.

**Example:**

```typescript
// ❌ Bad: Direct dependency on concrete class
class UserController {
  private repository = new UserRepository(); // Tight coupling!

  async getUsers() {
    return await this.repository.findAll();
  }
}

// ✅ Good: Depend on abstraction
interface UserRepositoryInterface {
  findAll(): Promise<User[]>;
}

class UserController {
  constructor(private repository: UserRepositoryInterface) {}

  async getUsers() {
    return await this.repository.findAll();
  }
}
```

**Benefits:**

- ✅ Easier to test (mock interfaces)
- ✅ Easier to swap implementations
- ✅ Decouples business logic from framework

---

## Additional Design Principles

### KISS (Keep It Simple, Stupid)

**Principle:** Simple solutions are better than complex ones.

**Questions to ask:**

- 🤔 Can I solve this in fewer lines?
- 🤔 Will a junior developer understand this in 6 months?
- 🤔 Am I adding complexity that's not needed yet?

**Example:**

```typescript
// ❌ Bad: Over-engineered
class UserNameFormatterFactoryBuilderProvider {
  createFormatterFactory(): UserNameFormatterFactory {
    return new UserNameFormatterFactory(new FormatterConfigurationBuilder());
  }
}

// ✅ Good: Simple and direct
function formatUserName(user: User): string {
  return `${user.firstName} ${user.lastName}`;
}
```

---

### YAGNI (You Aren't Gonna Need It)

**Principle:** Don't implement features until they're actually needed.

**When to add it:**

- ✅ When there's a concrete requirement
- ✅ When it's in the current sprint/issue
- ❌ "Just in case we need it later"

**Example:**

```typescript
// ❌ Bad: Building for hypothetical future
class User {
  // "We might need this someday"
  exportFormats = ["csv", "json", "xml", "pdf", "excel"];

  exportAs(format: string) {
    /* ... */
  }
  importFrom(format: string) {
    /* ... */
  }
  syncWithExternalApi() {
    /* ... */
  }
}

// ✅ Good: Only what's needed NOW
class UserExportService {
  // Current requirement: Export as CSV
  exportToCsv(users: User[]): string {
    // Simple implementation for current need
  }
}
```

---

### Separation of Concerns

**Principle:** Different responsibilities should be in different places.

**Pattern:**

```text
Controller → Service → Repository → Model
    ↓           ↓          ↓          ↓
  HTTP       Business    Data      Database
  Layer      Logic       Access    Entity
```

**Benefits:**

- ✅ Easier to test (test each layer independently)
- ✅ Easier to change (swap implementations)
- ✅ Clearer responsibilities

---

### Fail Fast

**Principle:** Detect and report errors as early as possible.

**In Practice:**

```typescript
// ✅ Validate at entry point
function createSecret(data: CreateSecretDto): Secret {
  // Validation happens in DTO/Schema, controller never receives invalid data
}

// ✅ Use type hints (fail at compile time)
function processUser(user: User): void {
  // TypeScript ensures 'user' is correct type
}

// ✅ Guard clauses (fail early in method)
function updateSecret(secret: Secret, data: UpdateData): Secret {
  if (secret.isExpired()) {
    throw new SecretExpiredException("Cannot update expired secret");
  }

  if (!this.canUserEdit(secret)) {
    throw new UnauthorizedException("User cannot edit this secret");
  }

  // Now safe to proceed
  return secret.update(data);
}
```

---

## Security & Best Practices

### Security by Design

**Principle:** Security is not an afterthought - build it in from the start.

**Rules:**

1. **Always Validate Input**
   - Use DTOs/Form Requests/Zod schemas
   - Never trust user input

2. **Never Log Sensitive Data**
   - ❌ Don't: `logger.info('Password:', password)`
   - ✅ Do: `logger.info('User authenticated', { userId })`

3. **Encrypt at Rest**
   - Use encryption casts/transformers
   - Store sensitive data encrypted

4. **Authorization at Multiple Layers**
   - Middleware checks permissions
   - Controllers double-check with policies
   - Services validate business rules

**Example:**

```typescript
// ✅ Multi-layer security
@UseGuards(AuthGuard, PermissionGuard) // Middleware layer
@Controller("secrets")
class SecretsController {
  @Post()
  async create(
    @Body() data: CreateSecretDto, // Input validation layer
    @CurrentUser() user: User
  ) {
    this.authService.authorize(user, "secrets.create"); // Policy layer
    return await this.secretsService.create(user, data);
  }
}
```

---

### Convention over Configuration

**Principle:** Follow framework conventions to reduce boilerplate.

**Benefits:**

- ✅ Less code to write
- ✅ Easier onboarding (everyone knows the conventions)
- ✅ Better tooling support

**Examples:**

| Framework      | Convention                            | Example                                |
| -------------- | ------------------------------------- | -------------------------------------- |
| **Laravel**    | Models singular, tables plural        | `User` model → `users` table           |
| **Laravel**    | Foreign keys: `{model}_id`            | `user_id`, `tenant_id`                 |
| **Laravel**    | Controllers plural                    | `UsersController`, `SecretsController` |
| **React**      | Components PascalCase                 | `UserProfile.tsx`, `SecretList.tsx`    |
| **React**      | Hooks start with `use`                | `useAuth()`, `useSecrets()`            |
| **TypeScript** | Interfaces with `I` prefix (optional) | `IUserRepository`                      |

---

## Framework-Specific Guidelines

### Laravel (Backend)

**Code Style:**

- ✅ PSR-12 (auto-format with Pint)
- ✅ Type hints for all parameters and returns
- ✅ Use Eloquent relationships over raw queries
- ✅ Use Form Requests for validation

**Testing:**

- ✅ Pest framework (never PHPUnit directly)
- ✅ Feature tests for controllers
- ✅ Unit tests for services/repositories
- ✅ ≥80% coverage target

**Commands:**

```bash
# Run tests
php artisan test

# Code style
./vendor/bin/pint

# Static analysis
./vendor/bin/phpstan analyse
```

---

### React/TypeScript (Frontend)

**Code Style:**

- ✅ ESLint + Prettier (auto-format)
- ✅ Functional components + hooks
- ✅ TypeScript strict mode
- ✅ Avoid `any` type

**Testing:**

- ✅ Vitest for unit tests
- ✅ React Testing Library for component tests
- ✅ E2E tests with Playwright (when needed)

**Commands:**

```bash
# Run tests
npm test

# Type check
npm run type-check

# Lint
npm run lint
```

---

## Practical Application

### Before Writing Code

1. ✅ Is there a test? (TDD)
2. ✅ Does similar code exist? (DRY)
3. ✅ Am I keeping it simple? (KISS)
4. ✅ Do I actually need this now? (YAGNI)

### While Writing Code

1. ✅ One responsibility per class? (SRP)
2. ✅ Using interfaces/abstractions? (DIP)
3. ✅ Validating input? (Fail Fast)
4. ✅ Following framework conventions?

### Before Pushing Code

1. ✅ All tests passing?
2. ✅ Linters/formatters passed?
3. ✅ Static analysis clean?
4. ✅ REUSE compliant?
5. ✅ Refactored code I touched? (Clean Before Quick)

```bash
# One command to check everything
./scripts/preflight.sh
```

---

## Related Documentation

### Organization-Wide (`.github` repo)

- [copilot-config.yaml](../.github/copilot-config.yaml) - Machine-readable source of truth
- [CONTRIBUTING.md](../CONTRIBUTING.md) - How to contribute
- [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md) - Community standards

### Repository-Specific

- **api**: `api/DEVELOPMENT.md` - Laravel setup & guidelines
- **frontend**: `frontend/DEVELOPMENT.md` - React setup & guidelines
- **contracts**: `contracts/README.md` - OpenAPI specifications

---

## Exceptions to Rules

**Remember:** These principles are guidelines, not laws.

**When to deviate:**

- 🤔 Performance-critical code (document why)
- 🤔 Legacy code integration (create tech debt issue)
- 🤔 Third-party library constraints (document workaround)

**Always:**

- ✅ Document the deviation in code comments
- ✅ Explain rationale in PR description
- ✅ Create tech debt issue if temporary

---

**Last Updated:** November 23, 2025
**Maintained by:** SecPal Organization
**Source of Truth:** [`.github/copilot-config.yaml`](../.github/copilot-config.yaml)
