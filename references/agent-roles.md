# Agent Role Templates

Reference templates for defining agent roles in a otaman-managed project. Use these as starting points when assigning owners in `platform.yaml`.

## Developer Agents

### backend-agent
- **Role**: Backend service development
- **Typical tech**: Node.js, Python, Go, Java, C#
- **Owns**: API services, business logic, database migrations, server-side utilities
- **Reads**: API contracts, shared types, specs, frontend repos (for integration context)
- **Sends**: `contract-change` when APIs change, `question` for frontend integration, `spec-change-request` when discovering missing endpoints

### frontend-agent
- **Role**: Frontend/UI development
- **Typical tech**: React, Vue, Angular, Svelte, Next.js
- **Owns**: Web applications, UI components, client-side state, API client code
- **Reads**: API contracts, design specs, backend repos (for API understanding)
- **Sends**: `contract-change` when shared types change, `spec-change-request` when discovering UI/UX gaps

### mobile-agent
- **Role**: Mobile application development
- **Typical tech**: React Native, Flutter, Swift, Kotlin
- **Owns**: Mobile apps, native modules, mobile-specific API clients
- **Reads**: API contracts, design specs, shared component repos
- **Sends**: `contract-change` for mobile-specific API needs, `question` for platform compatibility

### data-agent
- **Role**: Data pipeline and analytics
- **Typical tech**: Python, Airflow, Spark, dbt, SQL
- **Owns**: ETL pipelines, data models, analytics queries, data validation
- **Reads**: Database schemas, API contracts (for data source understanding)
- **Sends**: `contract-change` when data models change, `info` for pipeline status

### ml-agent
- **Role**: Machine learning model development
- **Typical tech**: Python, PyTorch, TensorFlow, scikit-learn
- **Owns**: ML models, training pipelines, model serving endpoints, feature engineering
- **Reads**: Data pipeline outputs, API contracts for model serving
- **Sends**: `contract-change` when model APIs change, `spec-change-request` for new model endpoints

### devops-agent
- **Role**: Infrastructure and CI/CD
- **Typical tech**: Terraform, Kubernetes, Docker, GitHub Actions
- **Owns**: Infrastructure configs, CI/CD pipelines, deployment scripts, monitoring
- **Reads**: All repos (for deployment context), dependency files
- **Sends**: `info` for infrastructure changes, `review-request` for security-sensitive infra

### specs-agent
- **Role**: Specification management (rare — usually humans manage specs)
- **Typical tech**: Markdown, OpenAPI, OpenSpec
- **Owns**: Specs repo (if delegated by human)
- **Reads**: All repos (for spec accuracy validation)
- **Sends**: `spec-change` broadcasts when specs are updated

## Observer Agents (Read-Only)

Observers never write to production repos. They review changes and write findings to `.agents/reviews/`.

### cto-reviewer
- **Triggers**: `pr`, `spec-change`, `architecture-change`
- **Reviews**: Architecture decisions, cross-repo impact, design quality, ADR compliance
- **Output**: Architecture review reports with severity ratings

### security
- **Triggers**: `pr`, `dependency-update`, `auth-change`
- **Reviews**: OWASP Top 10, dependency vulnerabilities, auth/access control, data exposure
- **Output**: Security findings with CVSS-like severity ratings

### devops (observer)
- **Triggers**: `infra-change`, `dockerfile-change`, `ci-change`
- **Reviews**: Infrastructure security, container best practices, CI/CD pipeline integrity
- **Output**: DevOps review reports with remediation suggestions

## Custom Roles

You can define any role name in `platform.yaml`. Use a descriptive `{domain}-agent` pattern:

```yaml
repos:
  - name: payment-service
    path: ./repo-payment
    owner: billing-agent       # Custom role
    tech: [nodejs, stripe-sdk]
```

The role name is used for:
- Ownership enforcement (only this agent writes to the repo)
- Message routing (`to: billing-agent` in bus messages)
- Agent identity (`.agents/current-agent` file)
- Git branch naming (`agent/billing-agent/feature-name`)
