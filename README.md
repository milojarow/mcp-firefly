# Firefly III MCP Server

A Model Context Protocol (MCP) server that provides AI assistants with safe, comprehensive access to your self-hosted Firefly III personal finance manager.

## Purpose

This MCP server enables AI assistants (like Claude) to help you manage your personal finances by:
- Recording transactions (expenses, income, transfers)
- Managing accounts, budgets, categories, and tags
- Analyzing spending patterns and financial data
- Organizing and categorizing your financial records

## Features

### 100% Complete API Coverage - 236 Tools

This MCP server provides **100% complete coverage** of the Firefly III REST API - all 229 base methods across all 28 API classes.

**System & Health (3 tools):**
- `health_check` - Verify API connectivity and authentication
- `get_system_info` - Get Firefly III version, user info, and system details
- `get_cron_status` - Get cron job status and configuration

**Account Management (9 tools):**
- `list_accounts` - List all accounts with optional type and name filtering
- `get_account_details` - Get detailed information for a specific account
- `create_account` - Create a new account (asset, expense, revenue, etc.)
- `update_account` - Update account name, active status, or notes
- `delete_account` - Delete an account (requires confirmation)
- `list_account_transactions` - List all transactions for a specific account
- `list_attachments_by_account` - List all attachments for an account
- `list_piggy_banks_by_account` - List piggy banks linked to an account

**Transaction Operations (14 tools):**
- `list_transactions` - List transactions with date range and type filtering
- `get_transaction_details` - Get detailed information for a transaction
- `create_withdrawal` - Create an expense transaction with full metadata
- `create_deposit` - Create an income transaction with full metadata
- `create_transfer` - Create a transfer between asset accounts
- `update_transaction` - Update existing transaction details
- `delete_transaction` - Delete a transaction (requires confirmation)
- `list_transactions_for_period` - List transactions within a specific time period
- `list_transactions_without_budget` - Find unbudgeted transactions
- `list_transactions_without_category` - Find uncategorized transactions
- `delete_transaction_journal` - Delete transaction by journal ID
- `get_transaction_by_journal` - Get transaction by journal ID
- `list_transaction_events` - List audit log events for a transaction
- `list_transaction_links_by_journal` - List links for a transaction journal

**Budget Management (15 tools):**
- `list_budgets` - List all budgets
- `get_budget_details` - Get detailed budget information
- `create_budget` - Create a new budget
- `update_budget` - Update budget details
- `delete_budget` - Delete a budget (requires confirmation)
- `list_budget_limits` - List spending limits for a budget
- `get_budget_spending` - Get spending data for a budget in a period
- `list_transactions_by_budget` - List all transactions in a budget
- `get_budget_limit_details` - Get details for a specific budget limit
- `list_all_budget_limits` - List all budget limits across all budgets
- `create_budget_limit` - Create a new budget limit
- `update_budget_limit` - Update an existing budget limit
- `delete_budget_limit` - Delete a budget limit
- `list_attachments_by_budget` - List all attachments for a budget
- `list_transactions_by_budget_limit` - List transactions for a specific budget limit

**Category Management (7 tools):**
- `list_categories` - List all categories
- `get_category_details` - Get detailed category information
- `create_category` - Create a new category
- `update_category` - Update category details
- `delete_category` - Delete a category (requires confirmation)
- `list_transactions_by_category` - List all transactions in a category
- `list_attachments_by_category` - List all attachments for a category

**Tag Management (6 tools):**
- `list_tags` - List all tags
- `get_tag_details` - Get detailed tag information
- `create_tag` - Create a new tag with optional date and description
- `update_tag` - Update tag details
- `delete_tag` - Delete a tag (requires confirmation)
- `list_transactions_by_tag` - List all transactions with a specific tag

**Bills (6 tools):**
- `list_bills` - List all bills with optional active/inactive filtering
- `get_bill_details` - Get detailed information for a bill
- `create_bill` - Create a new bill
- `update_bill` - Update bill details
- `delete_bill` - Delete a bill (requires confirmation)
- `list_bill_transactions` - List all transactions associated with a bill
- `list_attachments_by_bill` - List all attachments for a bill
- `list_rules_by_bill` - List all rules that reference a bill

**Piggy Banks (7 tools):**
- `list_piggy_banks` - List all piggy banks
- `get_piggy_bank_details` - Get detailed information for a piggy bank
- `create_piggy_bank` - Create a new piggy bank
- `update_piggy_bank` - Update piggy bank details
- `delete_piggy_bank` - Delete a piggy bank (requires confirmation)
- `list_piggy_bank_events` - List all events for a piggy bank
- `list_attachments_by_piggy_bank` - List all attachments for a piggy bank

**Autocomplete (15 tools):**
- `autocomplete_accounts` - Get account name suggestions
- `autocomplete_categories` - Get category name suggestions
- `autocomplete_tags` - Get tag name suggestions
- `autocomplete_budgets` - Get budget name suggestions
- `autocomplete_currencies` - Get currency suggestions
- `autocomplete_currency_codes` - Get currency code suggestions
- `autocomplete_object_groups` - Get object group suggestions
- `autocomplete_piggy_banks_with_balance` - Get piggy bank suggestions with balance
- `autocomplete_recurring_transactions` - Get recurring transaction suggestions
- `autocomplete_rule_groups` - Get rule group suggestions
- `autocomplete_rules` - Get rule suggestions
- `autocomplete_subscriptions` - Get subscription (bill) suggestions
- `autocomplete_transaction_types` - Get transaction type suggestions
- `autocomplete_transactions` - Get transaction suggestions
- `autocomplete_transaction_ids` - Get transaction ID suggestions

**Currencies (17 tools):**
- `list_currencies` - List all currencies (enabled and disabled)
- `get_currency_details` - Get detailed information for a currency
- `enable_currency` - Enable a currency for use
- `disable_currency` - Disable a currency
- `set_default_currency` - Set the default currency for the system
- `delete_currency` - Delete a currency
- `get_primary_currency` - Get the primary (default) currency
- `set_primary_currency` - Set a currency as primary
- `create_currency` - Create a new currency
- `update_currency` - Update currency details
- `list_accounts_by_currency` - List accounts using a currency
- `list_available_budgets_by_currency` - List available budgets in a currency
- `list_bills_by_currency` - List bills in a currency
- `list_budget_limits_by_currency` - List budget limits in a currency
- `list_recurrences_by_currency` - List recurring transactions in a currency
- `list_rules_by_currency` - List rules referencing a currency
- `list_transactions_by_currency` - List transactions in a currency

**Search (3 tools):**
- `search_all` - Search across all Firefly III entities (accounts, transactions, etc.)
- `search_accounts_specific` - Search specifically for accounts with field filtering
- `search_transactions_specific` - Search specifically for transactions

**Insights (4 tools):**
- `spending_summary` - Get spending summary for a date range
- `income_summary` - Get income summary for a date range
- `net_flow_summary` - Get net cash flow (income - spending) for a period
- `insight_transfers_overview` - Get general overview of transfers between accounts

**Rules & Rule Groups (13 tools):**
- `list_rule_groups` - List all rule groups
- `get_rule_group_details` - Get detailed information for a rule group
- `create_rule_group` - Create a new rule group
- `update_rule_group` - Update rule group details
- `delete_rule_group` - Delete a rule group (requires confirmation)
- `list_rules` - List all rules with optional filtering by rule group
- `get_rule_details` - Get detailed information for a rule
- `create_rule` - Create a new rule with triggers and actions
- `update_rule` - Update rule details, triggers, and actions
- `delete_rule` - Delete a rule (requires confirmation)
- `test_rule` - Test a rule against existing transactions
- `trigger_rule` - Manually trigger a rule to run
- `fire_rule_group` - Fire (trigger) a rule group on existing transactions
- `test_rule_group` - Test a rule group without applying changes

**Recurrences (8 tools):**
- `list_recurrences` - List all recurring transactions
- `get_recurrence_details` - Get detailed information for a recurrence
- `create_recurrence` - Create a new recurring transaction
- `update_recurrence` - Update recurrence details
- `delete_recurrence` - Delete a recurrence (requires confirmation)
- `list_recurrence_transactions` - List actual transactions created by a recurrence
- `trigger_recurrence_now` - Manually trigger a recurrence to create transaction immediately

**Webhooks (14 tools):**
- `list_webhooks` - List all webhooks
- `get_webhook_details` - Get detailed information for a webhook
- `create_webhook` - Create a new webhook
- `update_webhook` - Update webhook details
- `delete_webhook` - Delete a webhook (requires confirmation)
- `trigger_webhook_test` - Trigger a test webhook call
- `list_webhook_messages` - List all messages sent by a webhook
- `delete_webhook_message` - Delete a webhook message
- `delete_webhook_message_attempt` - Delete a webhook message attempt
- `get_webhook_message` - Get details for a webhook message
- `get_webhook_message_attempt` - Get details for a webhook message attempt
- `list_webhook_message_attempts` - List all attempts for a webhook message
- `trigger_transaction_webhook` - Manually trigger webhook for a specific transaction

**Attachments (7 tools):**
- `list_attachments` - List all attachments
- `get_attachment_details` - Get detailed information for an attachment
- `delete_attachment` - Delete an attachment (requires confirmation)
- `download_attachment` - Download attachment file content
- `create_attachment` - Create a new attachment (without file upload)
- `update_attachment` - Update attachment metadata
- `upload_attachment_file` - Upload file content to an attachment (base64)

**Available Budgets (6 tools):**
- `list_available_budgets` - List all available budget amounts
- `get_available_budget_details` - Get detailed information for an available budget
- `create_available_budget` - Create a new available budget amount
- `update_available_budget` - Update available budget details
- `delete_available_budget` - Delete an available budget (requires confirmation)

**Links (11 tools):**
- `list_transaction_links` - List all transaction links
- `get_transaction_link_details` - Get detailed information for a transaction link
- `delete_transaction_link` - Delete a transaction link (requires confirmation)
- `list_transaction_link_types` - List all transaction link types
- `get_transaction_link_type` - Get details for a transaction link type
- `create_transaction_link_type` - Create a new transaction link type
- `update_transaction_link_type` - Update a transaction link type
- `delete_transaction_link_type` - Delete a transaction link type
- `list_transactions_by_link_type` - List transactions using a link type
- `create_transaction_link` - Create a link between two transactions
- `update_transaction_link_notes` - Update notes for a transaction link

**Preferences & Configuration (7 tools):**
- `list_preferences` - List all user preferences
- `get_preference` - Get a specific preference value
- `get_configuration` - Get Firefly III system configuration
- `create_preference` - Create a new user preference
- `update_preference` - Update an existing user preference
- `get_single_configuration_value` - Get a single configuration value by name
- `set_configuration_value` - Set a configuration value

**Data Export (2 tools):**
- `export_accounts` - Export accounts data in CSV format
- `export_transactions` - Export transactions data in CSV format

**Generic Escape Hatch (1 tool):**
- `firefly_raw_request` - Make arbitrary API requests for unsupported endpoints

**Charts (4 tools):**
- `get_chart_account_overview` - Chart data for account balance overview
- `get_chart_balance` - Chart data for account balance over time
- `get_chart_budget_overview` - Chart data for budget spending overview
- `get_chart_category_overview` - Chart data for category spending overview

**Currency Exchange Rates (12 tools):**
- `list_currency_exchange_rates` - List all exchange rates
- `get_currency_exchange_rate` - Get specific exchange rate details
- `get_exchange_rate_on_date` - Get rate for currency pair on date
- `list_exchange_rates_for_pair` - List rates for currency pair in date range
- `create_exchange_rate` - Create new exchange rate
- `create_exchange_rate_by_date` - Create rate for specific date
- `create_exchange_rate_by_pair` - Create rate by currency pair
- `update_exchange_rate` - Update existing exchange rate
- `update_exchange_rate_by_date` - Update rate for specific date
- `delete_exchange_rate` - Delete exchange rate
- `delete_exchange_rate_on_date` - Delete rate for specific date
- `delete_exchange_rates_for_pair` - Delete all rates for pair in range

**Data Operations (10 tools):**
- `bulk_update_transactions` - Bulk update multiple transactions
- `export_bills` - Export bills to CSV
- `export_budgets` - Export budgets to CSV
- `export_categories` - Export categories to CSV
- `export_piggy_banks` - Export piggy banks to CSV
- `export_recurring_transactions` - Export recurring transactions to CSV
- `export_rules` - Export rules to CSV
- `export_tags` - Export tags to CSV
- `destroy_data` - Soft delete specific data types
- `purge_data` - Permanently purge all data (DANGEROUS)

**Extended Insights (21 tools):**
- `insight_expense_asset` - Expense insights by asset account
- `insight_expense_bill` - Expense insights by bill
- `insight_expense_budget` - Expense insights by budget
- `insight_expense_category` - Expense insights by category
- `insight_expense_expense_account` - Expense insights by expense account
- `insight_expense_no_bill` - Expenses without bill
- `insight_expense_no_budget` - Expenses without budget
- `insight_expense_no_category` - Expenses without category
- `insight_expense_no_tag` - Expenses without tag
- `insight_expense_tag` - Expense insights by tag
- `insight_expense_total` - Total expense insights
- `insight_income_asset` - Income insights by asset account
- `insight_income_category` - Income insights by category
- `insight_income_no_category` - Income without category
- `insight_income_no_tag` - Income without tag
- `insight_income_revenue` - Income insights by revenue account
- `insight_income_tag` - Income insights by tag
- `insight_income_total` - Total income insights
- `insight_transfer_category` - Transfer insights by category
- `insight_transfer_no_category` - Transfers without category
- `insight_transfer_no_tag` - Transfers without tag
- `insight_transfer_tag` - Transfer insights by tag
- `insight_transfer_total` - Total transfer insights

**Object Groups (6 tools):**
- `list_object_groups` - List all object groups
- `get_object_group` - Get object group details
- `update_object_group` - Update object group
- `delete_object_group` - Delete object group
- `list_bills_by_object_group` - List bills in group
- `list_piggy_banks_by_object_group` - List piggy banks in group

**Summary (1 tool):**
- `get_basic_summary` - Get dashboard summary for date range

**User Groups (3 tools):**
- `list_user_groups` - List all user groups
- `get_user_group` - Get user group details
- `update_user_group` - Update user group

**Users (5 tools):**
- `list_users` - List all users (admin)
- `get_user` - Get user details
- `create_user` - Create new user (admin)
- `update_user` - Update user details (admin)
- `delete_user` - Delete user (admin)

## Prerequisites

- Python 3.8 or higher
- Claude Desktop
- Access to ~/.config/mcp-secrets.json for credentials
- A running Firefly III instance (self-hosted or cloud)
- Personal Access Token from your Firefly III instance

## Installation

See SECTION 2 below for complete step-by-step installation instructions.

## Usage Examples

In Claude Desktop, you can ask:

### Account Management
- "List all my asset accounts"
- "Show me details for my checking account"
- "Create a new savings account called 'Emergency Fund'"
- "What's the balance in account ID 1?"
- "Show me all transactions for my checking account"

### Transaction Management
- "Show me all transactions from this month"
- "Record a $50 grocery expense from my checking account"
- "Create a deposit of $2000 salary to my checking account"
- "Transfer $500 from checking to savings"
- "What are the details of transaction ID 123?"
- "Update transaction 456 to change the amount to $75"
- "Show me all uncategorized transactions"

### Budgets & Categories
- "List all my budgets"
- "Create a new budget called 'Groceries' for $500/month"
- "Show me how much I've spent in my Groceries budget this month"
- "Show me all categories"
- "Create a category for 'Transportation'"
- "List all transactions in the Groceries category"

### Tags
- "List all tags"
- "Create a tag for 'Business Trip' for today"
- "Show me all transactions tagged with 'Vacation'"

### Bills & Recurring Transactions
- "List all my bills"
- "Create a bill for Netflix, $15.99 monthly"
- "Show me all transactions for my electricity bill"
- "Create a recurring transaction for my rent"
- "List all active recurring transactions"

### Piggy Banks
- "List all my piggy banks"
- "Create a piggy bank for 'Vacation Fund' with target $5000"
- "Show me the history of my Emergency Fund piggy bank"

### Rules & Automation
- "List all my transaction rules"
- "Create a rule to automatically categorize Uber expenses as Transportation"
- "Test rule ID 5 to see what it would do"
- "Manually trigger rule 'Categorize Amazon'"

### Insights & Analysis
- "What was my total spending last month?"
- "Show me my income for this year"
- "Calculate my net cash flow for Q1"
- "Search for all transactions mentioning 'coffee'"

### Advanced Operations
- "List all webhook configurations"
- "Export all my transactions from 2024 to CSV"
- "Show me all available currencies"
- "List all my transaction links"

### Charts & Dashboards
- "Get chart data for my checking account balance over the last 3 months"
- "Show me budget spending chart for Q1"
- "Generate category overview chart for this year"
- "Get my basic financial summary for December"

### Exchange Rates
- "List all currency exchange rates"
- "What's the EUR to USD rate on 2024-12-01?"
- "Create an exchange rate: USD to MXN = 18.5"
- "Update exchange rate 42 to 19.2"

### Extended Insights
- "Show me expense insights for my checking account"
- "What are my expenses without any budget assigned?"
- "Give me income insights for the Salary category"
- "Show transfer insights for Business tag"

### Object Groups & Organization
- "List all object groups"
- "Show me all bills in object group 3"
- "Create an object group for subscription services"

### Multi-User & Admin
- "List all users" (admin only)
- "Create a new user with email john@example.com" (admin only)
- "List all user groups"

### Bulk Operations
- "Export all my budgets to CSV"
- "Export all rules to backup"
- "Bulk update these 10 transactions..."

## Architecture

```
Claude Desktop → Firefly III MCP Server (Python/venv) → Firefly III API
↓
~/.config/mcp-secrets.json
```

## Development

### Local Testing

```bash
# Ensure secrets are configured in ~/.config/mcp-secrets.json

# Activate virtual environment
source ~/.local/share/mcp-servers/mcp-firefly/venv/bin/activate

# Run directly
python firefly_server.py

# Test MCP protocol
echo '{"jsonrpc":"2.0","method":"tools/list","id":1}' | python firefly_server.py

# Deactivate venv
deactivate
```

### Adding New Tools

1. Add the function to `firefly_server.py`
2. Decorate with `@mcp.tool()`
3. If new dependencies needed, add to requirements.txt and reinstall:
   ```bash
   source venv/bin/activate
   pip install -r requirements.txt
   deactivate
   ```
4. Restart Claude Desktop

## Troubleshooting

### Tools Not Appearing
- Check Claude Desktop logs: `~/.config/Claude/logs/mcp.log`
- Verify server path in Claude config is correct
- Ensure venv is properly configured with all dependencies
- Check server runs without errors: `source venv/bin/activate && python firefly_server.py`
- Restart Claude Desktop

### Authentication Errors
- Verify ~/.config/mcp-secrets.json exists and has correct format
- Check permissions on secrets file (should be 600)
- Ensure "firefly" key exists in secrets file
- Verify base_url and token values are correct
- Test API access: `curl -H "Authorization: Bearer YOUR_TOKEN" https://your-firefly.com/api/v1/about`

### API Errors
- Check that your Firefly III instance is running and accessible
- Verify the base_url in secrets file is correct (should end with /api or let the server append it)
- Ensure your Personal Access Token has not expired
- Check Firefly III logs for any server-side errors

## Security Considerations

- All secrets stored in ~/.config/mcp-secrets.json with 600 permissions
- Never hardcode credentials in code
- Secrets file should never be committed to git
- Sensitive data never logged to stderr
- Server runs with user permissions (no root required)
- Destructive operations (delete) require explicit confirmation
- All API communication uses HTTPS (verify your Firefly III instance uses SSL)

## API Documentation

- Firefly III API Docs: https://api-docs.firefly-iii.org/
- Python Client: https://github.com/ms32035/firefly-iii-client
- Firefly III GitHub: https://github.com/firefly-iii/firefly-iii

## License

MIT License
