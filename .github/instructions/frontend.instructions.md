<!--
SPDX-FileCopyrightText: 2025 SecPal
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Frontend Instructions (React/TypeScript)

> **Note:** These instructions are organization-level defaults from `SecPal/.github`.
> Copy to `SecPal/frontend/.github/copilot-instructions.md` when frontend repo is created.

**Applies to:** `src/**`, `apps/**`, `packages/**`, `*.tsx`, `*.ts`

## Path-Scoped Rules (Preflight Integration)

<!--
These rules can be activated for local preflight checks in frontend repo:

applyTo:
  - "src/**"
  - "apps/**"
  - "packages/ui/**"

rules:
  - "React + TS; check accessibility (a11y); provide Storybook stories for new components."
  - "API access: RTK/TanStack Query; types from the OpenAPI generator."
-->

## Architecture

- Component-driven development
- Container/Presenter pattern (smart/dumb components)
- Custom hooks for shared logic
- Context for global state (minimize prop drilling)

## Code Style

```bash
# Lint
npm run lint

# Type check
npm run typecheck

# Format
npx prettier --write src/
```

**Rules:**

- Functional components only (no classes)
- Named exports (better for refactoring)
- One component per file
- Props interfaces above component

## TypeScript

**Strict mode enabled:**

```typescript
// ❌ Don't use 'any'
const data: any = await fetch();

// ✅ Do define proper types
interface User {
  id: string;
  email: string;
}
const data: User = await fetch();
```

**Common patterns:**

```typescript
// Props
interface ButtonProps {
  onClick: () => void;
  children: React.ReactNode;
  variant?: "primary" | "secondary";
}

// API responses (from OpenAPI-generated types)
// Note: To use the '@' path alias prefix (as in import statements like `import x from '@/...'`), configure your project as follows:
// In tsconfig.json, add the following to map '@/*' to 'src/*':
//   "compilerOptions": {
//     "baseUrl": ".",
//     "paths": {
//       "@/*": ["src/*"]
//     }
//   }
// If using Vite, also add to vite.config.ts:
//   import { defineConfig } from 'vite';
//   import path from 'path';
//   export default defineConfig({
//     resolve: {
//       alias: {
//         '@': path.resolve(__dirname, 'src'),
//       },
//     },
//   });
import type { User } from "@/types/api";

// Hooks return type
function useUser(id: string): {
  user: User | null;
  loading: boolean;
  error: Error | null;
} {
  // ...
}
```

## Testing

```bash
# Run all tests
npm test

# Watch mode
npm test -- --watch

# Coverage
npm test -- --coverage
```

**Requirements:**

- Test user-visible behavior (not implementation)
- Use `@testing-library/react` queries
- Mock API calls with MSW
- Aim for 80%+ coverage

**Example:**

```typescript
import { render, screen } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";

test("submits form with user input", async () => {
  render(<LoginForm />);

  await userEvent.type(screen.getByLabelText(/email/i), "test@example.com");
  await userEvent.click(screen.getByRole("button", { name: /login/i }));

  expect(await screen.findByText(/welcome/i)).toBeInTheDocument();
});
```

## State Management

**Prefer React built-ins:**

- `useState` for local state
- `useContext` for shared state
- `useReducer` for complex state logic

**External libraries (if needed):**

- Zustand (lightweight, TypeScript-first)
- TanStack Query (server state)

## API Integration

```typescript
// Use OpenAPI-generated types
import type { User, CreateUserRequest } from "@/types/api";

// Fetch wrapper with types
async function createUser(data: CreateUserRequest): Promise<User> {
  const response = await fetch("/api/v1/users", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }

  return response.json();
}
```

## Performance

- Lazy load routes (`React.lazy`)
- Memoize expensive computations (`useMemo`)
- Debounce user input
- Virtual scrolling for long lists
- Code split by route

## Accessibility

- Semantic HTML elements
- ARIA labels when needed
- Keyboard navigation
- Focus management
- Color contrast (WCAG AA)

**Test with:**

```bash
# Run accessibility tests
npm test -- --testNamePattern="a11y"
```

## Styling

- CSS Modules or Tailwind CSS
- Mobile-first responsive design
- Dark mode support
- Consistent spacing (use design tokens)

## Error Handling

```typescript
// Error boundaries for crashes
<ErrorBoundary fallback={<ErrorPage />}>
  <App />
</ErrorBoundary>;

// Loading states
if (loading) return <Spinner />;
if (error) return <ErrorMessage error={error} />;

// Empty states
if (data.length === 0) return <EmptyState />;
```

## Resources

- [React Docs](https://react.dev)
- [TypeScript Handbook](https://www.typescriptlang.org/docs)
- [Testing Library](https://testing-library.com/react)
- [Vite Guide](https://vitejs.dev/guide)
