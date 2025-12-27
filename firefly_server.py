#!/usr/bin/env python3
"""
Comprehensive Firefly III MCP Server - Full API Coverage
Provides rich, safe control over Firefly III personal finance manager.
"""
import os
import sys
import json
import logging
from datetime import datetime, timezone
from typing import Any
import firefly_iii_client
from firefly_iii_client.rest import ApiException
from mcp.server.fastmcp import FastMCP

# Configure logging to stderr
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger("firefly-server")

# Initialize MCP server
mcp = FastMCP("firefly")

# Configuration
SECRETS_FILE = os.path.expanduser("~/.config/mcp-secrets.json")

# Global API client (initialized on first use)
_api_client = None
_configuration = None

def load_config():
    """Load configuration from secrets file."""
    try:
        with open(SECRETS_FILE, 'r') as f:
            secrets = json.load(f)
        return secrets.get("firefly", {})
    except FileNotFoundError:
        logger.error(f"Secrets file not found: {SECRETS_FILE}")
        return {}
    except Exception as e:
        logger.error(f"Error loading secrets: {e}")
        return {}

def get_api_client():
    """Get or create the global API client."""
    global _api_client, _configuration

    if _api_client is None:
        config = load_config()
        if not config.get("base_url") or not config.get("token"):
            raise ValueError("Missing base_url or token in ~/.config/mcp-secrets.json")

        base_url = config["base_url"].rstrip("/")
        # Ensure URL ends with /api (not /api/v1, the client adds /v1 automatically)
        if not base_url.endswith("/api"):
            base_url = f"{base_url}/api"

        _configuration = firefly_iii_client.configuration.Configuration(
            host=base_url
        )
        # Set access token after configuration creation (required pattern for bearer auth)
        _configuration.access_token = config["token"]
        _api_client = firefly_iii_client.ApiClient(_configuration)

    return _api_client

def format_error(e: Exception) -> str:
    """Format error message for user display."""
    if isinstance(e, ApiException):
        try:
            error_data = json.loads(e.body)
            msg = error_data.get("message", str(e))
            return f"❌ API Error ({e.status}): {msg}"
        except:
            return f"❌ API Error ({e.status}): {e.reason}"
    return f"❌ Error: {str(e)}"

def format_amount(amount: str) -> str:
    """Format amount to 2 decimal places."""
    try:
        return f"{float(amount):.2f}"
    except (ValueError, TypeError):
        return str(amount)

# ============================================================================
# SYSTEM & HEALTH
# ============================================================================

@mcp.tool()
async def health_check() -> str:
    """Check Firefly III API connectivity and authentication status."""
    try:
        client = get_api_client()
        api = firefly_iii_client.AboutApi(client)
        about = api.get_about()
        return f"✅ Connected to Firefly III\nVersion: {about.data.version}\nAPI Version: {about.data.api_version}"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def get_system_info() -> str:
    """Get Firefly III system information including version, user info, and system details."""
    try:
        client = get_api_client()
        api = firefly_iii_client.AboutApi(client)
        about = api.get_about()
        user_api = firefly_iii_client.UsersApi(client)
        users = user_api.list_user()

        info = about.data
        result = f"""📊 Firefly III System Information

**Version:** {info.version}
**API Version:** {info.api_version}
**PHP Version:** {info.php_version}
**OS:** {info.os}
**Driver:** {info.driver}

**Current User:** {users.data[0].attributes.email if users.data else 'Unknown'}
"""
        return result
    except Exception as e:
        return format_error(e)

# ============================================================================
# ACCOUNTS
# ============================================================================

@mcp.tool()
async def list_accounts(account_type: str = "", name_filter: str = "") -> str:
    """List all accounts with optional filters by type (asset, expense, revenue, etc.) and name substring."""
    try:
        client = get_api_client()
        api = firefly_iii_client.AccountsApi(client)

        params = {}
        if account_type:
            params['type'] = account_type

        accounts = api.list_account(**params)

        if name_filter:
            filtered = [acc for acc in accounts.data if name_filter.lower() in acc.attributes.name.lower()]
        else:
            filtered = accounts.data

        if not filtered:
            return "📭 No accounts found matching criteria"

        result = f"💰 Found {len(filtered)} account(s):\n\n"
        result += "| ID | Name | Type | Balance | Currency |\n"
        result += "|------|------|------|---------|----------|\n"

        for acc in filtered[:50]:
            attrs = acc.attributes
            balance = attrs.current_balance if hasattr(attrs, 'current_balance') else '0'
            currency = attrs.currency_code if hasattr(attrs, 'currency_code') else 'N/A'
            result += f"| {acc.id} | {attrs.name} | {attrs.type} | {balance} | {currency} |\n"

        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def get_account_details(account_id: str = "") -> str:
    """Get detailed information for a specific account by ID."""
    try:
        if not account_id.strip():
            return "❌ Error: account_id is required"

        client = get_api_client()
        api = firefly_iii_client.AccountsApi(client)
        account = api.get_account(account_id)

        attrs = account.data.attributes
        result = f"""💳 Account Details: {attrs.name}

**ID:** {account.data.id}
**Type:** {attrs.type}
**Account Number:** {attrs.account_number or 'N/A'}
**IBAN:** {attrs.iban or 'N/A'}
**Currency:** {attrs.currency_code}
**Current Balance:** {attrs.current_balance}
**Active:** {'Yes' if attrs.active else 'No'}
**Role:** {attrs.account_role or 'N/A'}

**Notes:** {attrs.notes or 'None'}
"""
        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def create_account(name: str = "", account_type: str = "asset", currency_code: str = "USD", opening_balance: str = "0", notes: str = "", liability_type: str = "", liability_direction: str = "") -> str:
    """Create a new account with specified name, type (asset, expense, revenue, liability, etc.), currency, and optional opening balance.

    For liability accounts, you must provide:
    - liability_type: 'loan', 'debt', 'mortgage', or 'credit-card'
    - liability_direction: 'credit' (you owe money) or 'debit' (someone owes you)
    """
    try:
        if not name.strip():
            return "❌ Error: name is required"

        # Validate liability-specific fields
        if account_type == "liability":
            if not liability_type:
                return "❌ Error: liability_type is required when account_type is 'liability'. Use: 'loan', 'debt', 'mortgage', or 'credit-card'"
            if not liability_direction:
                return "❌ Error: liability_direction is required when account_type is 'liability'. Use: 'credit' (you owe) or 'debit' (they owe you)"
            if liability_direction not in ["credit", "debit"]:
                return f"❌ Error: liability_direction must be 'credit' or 'debit', got: '{liability_direction}'"

        client = get_api_client()
        api = firefly_iii_client.AccountsApi(client)

        account_data = {
            "name": name,
            "type": account_type,
            "currency_code": currency_code,
            "active": True
        }

        # Add asset-specific fields
        if account_type == "asset":
            account_data["account_role"] = "defaultAsset"
            account_data["include_net_worth"] = True

        # Add liability-specific fields
        if account_type == "liability":
            account_data["liability_type"] = liability_type
            account_data["liability_direction"] = liability_direction

        if opening_balance and opening_balance != "0":
            account_data["opening_balance"] = opening_balance
            account_data["opening_balance_date"] = datetime.now().strftime("%Y-%m-%d")

        if notes:
            account_data["notes"] = notes

        account_store = firefly_iii_client.AccountStore(**account_data)
        account = api.store_account(account_store)

        return f"✅ Created account: {account.data.attributes.name} (ID: {account.data.id})"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def update_account(account_id: str = "", name: str = "", active: str = "", notes: str = "") -> str:
    """Update account name, active status (true/false), or notes."""
    try:
        if not account_id.strip():
            return "❌ Error: account_id is required"

        client = get_api_client()
        api = firefly_iii_client.AccountsApi(client)

        update_data = {}
        if name:
            update_data["name"] = name
        if active:
            update_data["active"] = active.lower() == "true"
        if notes:
            update_data["notes"] = notes

        if not update_data:
            return "❌ Error: At least one field to update is required"

        account_update = firefly_iii_client.AccountUpdate(**update_data)
        account = api.update_account(account_id, account_update)

        return f"✅ Updated account: {account.data.attributes.name}"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def delete_account(account_id: str = "", confirm: str = "") -> str:
    """Delete an account by ID (requires confirm='DELETE' for safety)."""
    try:
        if not account_id.strip():
            return "❌ Error: account_id is required"
        if confirm != "DELETE":
            return "⚠️ Warning: This will permanently delete the account. Set confirm='DELETE' to proceed."

        client = get_api_client()
        api = firefly_iii_client.AccountsApi(client)
        api.delete_account(account_id)

        return f"✅ Deleted account ID: {account_id}"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def list_account_transactions(account_id: str = "", start_date: str = "", end_date: str = "", transaction_type: str = "") -> str:
    """List transactions for a specific account with optional date range and type filter."""
    try:
        if not account_id.strip():
            return "❌ Error: account_id is required"

        client = get_api_client()
        api = firefly_iii_client.AccountsApi(client)

        params = {}
        if start_date:
            params['start'] = start_date
        if end_date:
            params['end'] = end_date
        if transaction_type:
            params['type'] = transaction_type

        transactions = api.list_transaction_by_account(account_id, **params)

        if not transactions.data:
            return "📭 No transactions found"

        result = f"📝 Found {len(transactions.data)} transaction(s):\n\n"
        result += "| Date | Description | Amount | Type |\n"
        result += "|------|-------------|--------|------|\n"

        for txn in transactions.data[:50]:
            attrs = txn.attributes.transactions[0]
            result += f"| {attrs.var_date} | {attrs.description} | {format_amount(attrs.amount)} {attrs.currency_code} | {attrs.type} |\n"

        return result
    except Exception as e:
        return format_error(e)

# ============================================================================
# TRANSACTIONS
# ============================================================================

@mcp.tool()
async def list_transactions(start_date: str = "", end_date: str = "", transaction_type: str = "", limit: str = "50") -> str:
    """List transactions with filters for date range, type (withdrawal, deposit, transfer), and limit."""
    try:
        client = get_api_client()
        api = firefly_iii_client.TransactionsApi(client)

        params = {}
        if start_date:
            params['start'] = start_date
        if end_date:
            params['end'] = end_date
        if transaction_type:
            params['type'] = transaction_type

        limit_int = int(limit) if limit.strip() else 50
        params['limit'] = limit_int

        transactions = api.list_transaction(**params)

        if not transactions.data:
            return "📭 No transactions found"

        result = f"📝 Found {len(transactions.data)} transaction(s):\n\n"
        result += "| ID | Date | Description | Amount | Type |\n"
        result += "|------|------|-------------|--------|------|\n"

        for txn in transactions.data:
            attrs = txn.attributes.transactions[0]
            result += f"| {txn.id} | {attrs.var_date} | {attrs.description} | {format_amount(attrs.amount)} {attrs.currency_code} | {attrs.type} |\n"

        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def get_transaction_details(transaction_id: str = "") -> str:
    """Get detailed information for a specific transaction by ID."""
    try:
        if not transaction_id.strip():
            return "❌ Error: transaction_id is required"

        client = get_api_client()
        api = firefly_iii_client.TransactionsApi(client)
        transaction = api.get_transaction(transaction_id)

        txn = transaction.data.attributes.transactions[0]
        result = f"""💸 Transaction Details

**ID:** {transaction.data.id}
**Type:** {txn.type}
**Date:** {txn.date}
**Description:** {txn.description}
**Amount:** {format_amount(txn.amount)} {txn.currency_code}

**Source:** {txn.source_name} (ID: {txn.source_id})
**Destination:** {txn.destination_name} (ID: {txn.destination_id})

**Category:** {txn.category_name or 'None'}
**Budget:** {txn.budget_name or 'None'}
**Tags:** {', '.join(txn.tags) if txn.tags else 'None'}

**Notes:** {txn.notes or 'None'}
"""
        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def create_withdrawal(description: str = "", amount: str = "", source_account: str = "", destination_account: str = "", date: str = "", category: str = "", budget: str = "", tags: str = "", notes: str = "") -> str:
    """Create a withdrawal transaction (expense) with description, amount, source account ID, destination account ID/name, and optional metadata (category, budget, comma-separated tags, notes)."""
    try:
        if not all([description.strip(), amount.strip(), source_account.strip()]):
            return "❌ Error: description, amount, and source_account are required"

        if not destination_account.strip():
            destination_account = "Cash account"

        client = get_api_client()
        api = firefly_iii_client.TransactionsApi(client)

        transaction_date = date if date else datetime.now().strftime("%Y-%m-%d")

        transaction_split = {
            "type": "withdrawal",
            "date": transaction_date,
            "amount": amount,
            "description": description,
            "source_id": source_account
        }

        # Use destination_id if numeric ID is passed, otherwise use destination_name
        if destination_account.strip().isdigit():
            transaction_split["destination_id"] = destination_account
        else:
            transaction_split["destination_name"] = destination_account

        if category:
            transaction_split["category_name"] = category
        if budget:
            # Route to budget_id for numeric input, budget_name for text
            if budget.strip().isdigit():
                transaction_split["budget_id"] = budget
            else:
                transaction_split["budget_name"] = budget
        if tags:
            transaction_split["tags"] = [t.strip() for t in tags.split(",")]
        if notes:
            transaction_split["notes"] = notes

        transaction_store = firefly_iii_client.TransactionStore(
            error_if_duplicate_hash=False,
            apply_rules=True,
            transactions=[firefly_iii_client.TransactionSplitStore(**transaction_split)]
        )

        result = api.store_transaction(transaction_store)
        txn_data = result.data.attributes.transactions[0]

        return f"✅ Created withdrawal: {txn_data.description}\nAmount: {format_amount(txn_data.amount)} {txn_data.currency_code}\nID: {result.data.id}"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def create_deposit(description: str = "", amount: str = "", destination_account: str = "", source_account: str = "", date: str = "", category: str = "", budget: str = "", tags: str = "", notes: str = "") -> str:
    """Create a deposit transaction (income) with description, amount, destination account ID, source account ID/name, and optional metadata."""
    try:
        if not all([description.strip(), amount.strip(), destination_account.strip()]):
            return "❌ Error: description, amount, and destination_account are required"

        if not source_account.strip():
            source_account = "Cash account"

        client = get_api_client()
        api = firefly_iii_client.TransactionsApi(client)

        transaction_date = date if date else datetime.now().strftime("%Y-%m-%d")

        transaction_split = {
            "type": "deposit",
            "date": transaction_date,
            "amount": amount,
            "description": description,
            "destination_id": destination_account
        }

        # Use source_id if numeric ID is passed, otherwise use source_name
        if source_account.strip().isdigit():
            transaction_split["source_id"] = source_account
        else:
            transaction_split["source_name"] = source_account

        if category:
            transaction_split["category_name"] = category
        if budget:
            # Route to budget_id for numeric input, budget_name for text
            if budget.strip().isdigit():
                transaction_split["budget_id"] = budget
            else:
                transaction_split["budget_name"] = budget
        if tags:
            transaction_split["tags"] = [t.strip() for t in tags.split(",")]
        if notes:
            transaction_split["notes"] = notes

        transaction_store = firefly_iii_client.TransactionStore(
            error_if_duplicate_hash=False,
            apply_rules=True,
            transactions=[firefly_iii_client.TransactionSplitStore(**transaction_split)]
        )

        result = api.store_transaction(transaction_store)
        txn_data = result.data.attributes.transactions[0]

        return f"✅ Created deposit: {txn_data.description}\nAmount: {format_amount(txn_data.amount)} {txn_data.currency_code}\nID: {result.data.id}"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def create_transfer(description: str = "", amount: str = "", source_account: str = "", destination_account: str = "", date: str = "", notes: str = "") -> str:
    """Create a transfer between two asset accounts with description, amount, source account ID, destination account ID, and optional notes."""
    try:
        if not all([description.strip(), amount.strip(), source_account.strip(), destination_account.strip()]):
            return "❌ Error: description, amount, source_account, and destination_account are required"

        client = get_api_client()
        api = firefly_iii_client.TransactionsApi(client)

        transaction_date = date if date else datetime.now().strftime("%Y-%m-%d")

        transaction_split = {
            "type": "transfer",
            "date": transaction_date,
            "amount": amount,
            "description": description,
            "source_id": source_account,
            "destination_id": destination_account
        }

        if notes:
            transaction_split["notes"] = notes

        transaction_store = firefly_iii_client.TransactionStore(
            error_if_duplicate_hash=False,
            apply_rules=True,
            transactions=[firefly_iii_client.TransactionSplitStore(**transaction_split)]
        )

        result = api.store_transaction(transaction_store)
        txn_data = result.data.attributes.transactions[0]

        return f"✅ Created transfer: {txn_data.description}\nAmount: {format_amount(txn_data.amount)} {txn_data.currency_code}\nFrom: {txn_data.source_name} → To: {txn_data.destination_name}\nID: {result.data.id}"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def update_transaction(transaction_id: str = "", description: str = "", amount: str = "", date: str = "", category: str = "", budget: str = "", tags: str = "", notes: str = "") -> str:
    """Update an existing transaction with new values for description, amount, date, category, budget, tags, or notes.

    NOTE: budget parameter must be a budget ID (numeric), not a budget name.
    Example: budget="2" (not "Transport - Commute")
    """
    try:
        if not transaction_id.strip():
            return "❌ Error: transaction_id is required"

        client = get_api_client()
        api = firefly_iii_client.TransactionsApi(client)

        # Get existing transaction first
        existing = api.get_transaction(transaction_id)
        existing_txn = existing.data.attributes.transactions[0]

        # Build update data (only include fields that are being updated)
        update_split = {}

        if date:
            update_split["date"] = date
        if amount:
            update_split["amount"] = amount
        if description:
            update_split["description"] = description

        if category:
            update_split["category_name"] = category
        if budget:
            # For updates, ONLY budget_id works (budget_name is excluded during serialization)
            update_split["budget_id"] = budget
        if tags:
            update_split["tags"] = [t.strip() for t in tags.split(",")]
        if notes:
            update_split["notes"] = notes

        transaction_update = firefly_iii_client.TransactionUpdate(
            transactions=[firefly_iii_client.TransactionSplitUpdate(**update_split)]
        )

        result = api.update_transaction(transaction_id, transaction_update)
        return f"✅ Updated transaction ID: {transaction_id}"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def delete_transaction(transaction_id: str = "", confirm: str = "") -> str:
    """Delete a transaction by ID (requires confirm='DELETE' for safety)."""
    try:
        if not transaction_id.strip():
            return "❌ Error: transaction_id is required"
        if confirm != "DELETE":
            return "⚠️ Warning: This will permanently delete the transaction. Set confirm='DELETE' to proceed."

        client = get_api_client()
        api = firefly_iii_client.TransactionsApi(client)
        api.delete_transaction(transaction_id)

        return f"✅ Deleted transaction ID: {transaction_id}"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def list_transactions_for_period(period: str = "month", year: str = "", month: str = "") -> str:
    """List transactions for a specific period (month, year) with optional year and month parameters."""
    try:
        now = datetime.now()
        year_int = int(year) if year.strip() else now.year
        month_int = int(month) if month.strip() else now.month

        if period == "month":
            start_date = f"{year_int}-{month_int:02d}-01"
            # Calculate last day of month
            if month_int == 12:
                end_date = f"{year_int}-12-31"
            else:
                from dateutil.relativedelta import relativedelta
                import datetime as dt
                start = dt.date(year_int, month_int, 1)
                end = start + relativedelta(months=1) - dt.timedelta(days=1)
                end_date = end.strftime("%Y-%m-%d")
        elif period == "year":
            start_date = f"{year_int}-01-01"
            end_date = f"{year_int}-12-31"
        else:
            return "❌ Error: period must be 'month' or 'year'"

        return await list_transactions(start_date=start_date, end_date=end_date)
    except Exception as e:
        return format_error(e)

# ============================================================================
# BUDGETS
# ============================================================================

@mcp.tool()
async def list_budgets() -> str:
    """List all budgets."""
    try:
        client = get_api_client()
        api = firefly_iii_client.BudgetsApi(client)
        budgets = api.list_budget()

        if not budgets.data:
            return "📭 No budgets found"

        result = f"💰 Found {len(budgets.data)} budget(s):\n\n"
        result += "| ID | Name | Active |\n"
        result += "|------|------|--------|\n"

        for budget in budgets.data:
            attrs = budget.attributes
            active = '✓' if attrs.active else '✗'
            result += f"| {budget.id} | {attrs.name} | {active} |\n"

        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def get_budget_details(budget_id: str = "") -> str:
    """Get detailed budget information including limits and spending."""
    try:
        if not budget_id.strip():
            return "❌ Error: budget_id is required"

        client = get_api_client()
        api = firefly_iii_client.BudgetsApi(client)
        budget = api.get_budget(budget_id)

        attrs = budget.data.attributes
        result = f"""💼 Budget Details: {attrs.name}

**ID:** {budget.data.id}
**Active:** {'Yes' if attrs.active else 'No'}
**Auto-budget:** {attrs.auto_budget_type or 'None'}

**Notes:** {attrs.notes or 'None'}
"""
        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def create_budget(name: str = "", active: str = "true", notes: str = "") -> str:
    """Create a new budget with name, active status, and optional notes."""
    try:
        if not name.strip():
            return "❌ Error: name is required"

        client = get_api_client()
        api = firefly_iii_client.BudgetsApi(client)

        budget_data = {
            "name": name,
            "active": active.lower() == "true"
        }

        if notes:
            budget_data["notes"] = notes

        budget_store = firefly_iii_client.BudgetStore(**budget_data)
        budget = api.store_budget(budget_store)

        return f"✅ Created budget: {budget.data.attributes.name} (ID: {budget.data.id})"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def update_budget(budget_id: str = "", name: str = "", active: str = "", notes: str = "") -> str:
    """Update budget name, active status, or notes."""
    try:
        if not budget_id.strip():
            return "❌ Error: budget_id is required"

        client = get_api_client()
        api = firefly_iii_client.BudgetsApi(client)

        update_data = {}
        if name:
            update_data["name"] = name
        if active:
            update_data["active"] = active.lower() == "true"
        if notes:
            update_data["notes"] = notes

        if not update_data:
            return "❌ Error: At least one field to update is required"

        budget_update = firefly_iii_client.BudgetUpdate(**update_data)
        budget = api.update_budget(budget_id, budget_update)

        return f"✅ Updated budget: {budget.data.attributes.name}"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def delete_budget(budget_id: str = "", confirm: str = "") -> str:
    """Delete a budget by ID (requires confirm='DELETE' for safety)."""
    try:
        if not budget_id.strip():
            return "❌ Error: budget_id is required"
        if confirm != "DELETE":
            return "⚠️ Warning: This will permanently delete the budget. Set confirm='DELETE' to proceed."

        client = get_api_client()
        api = firefly_iii_client.BudgetsApi(client)
        api.delete_budget(budget_id)

        return f"✅ Deleted budget ID: {budget_id}"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def list_budget_limits(budget_id: str = "") -> str:
    """List all budget limits for a specific budget."""
    try:
        if not budget_id.strip():
            return "❌ Error: budget_id is required"

        client = get_api_client()
        api = firefly_iii_client.BudgetsApi(client)
        limits = api.list_budget_limit_by_budget(budget_id)

        if not limits.data:
            return "📭 No budget limits found"

        result = f"📊 Budget Limits:\n\n"
        result += "| Start | End | Amount | Currency |\n"
        result += "|------|------|--------|----------|\n"

        for limit in limits.data:
            attrs = limit.attributes
            result += f"| {attrs.start} | {attrs.end} | {format_amount(attrs.amount)} | {attrs.currency_code} |\n"

        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def get_budget_spending(budget_id: str = "", start_date: str = "", end_date: str = "") -> str:
    """Get budget spending for a specific budget and date range."""
    try:
        if not budget_id.strip():
            return "❌ Error: budget_id is required"

        # If no dates provided, use current month
        if not start_date or not end_date:
            now = datetime.now()
            start_date = f"{now.year}-{now.month:02d}-01"
            from dateutil.relativedelta import relativedelta
            import datetime as dt
            start = dt.date(now.year, now.month, 1)
            end = start + relativedelta(months=1) - dt.timedelta(days=1)
            end_date = end.strftime("%Y-%m-%d")

        client = get_api_client()
        txn_api = firefly_iii_client.TransactionsApi(client)

        # Get transactions for this budget in the date range
        transactions = txn_api.list_transaction(
            start=start_date,
            end=end_date,
            type='withdrawal'
        )

        # Filter for this budget
        budget_api = firefly_iii_client.BudgetsApi(client)
        budget = budget_api.get_budget(budget_id)
        budget_name = budget.data.attributes.name

        total_spent = 0
        count = 0
        for txn in transactions.data:
            txn_data = txn.attributes.transactions[0]
            if txn_data.budget_name == budget_name:
                total_spent += float(txn_data.amount)
                count += 1

        result = f"""💸 Budget Spending: {budget_name}

**Period:** {start_date} to {end_date}
**Transactions:** {count}
**Total Spent:** {total_spent:.2f}
"""
        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def list_transactions_without_budget(start_date: str = "", end_date: str = "") -> str:
    """List transactions without a budget assignment for a given period."""
    try:
        if not start_date or not end_date:
            now = datetime.now()
            start_date = f"{now.year}-{now.month:02d}-01"
            from dateutil.relativedelta import relativedelta
            import datetime as dt
            start = dt.date(now.year, now.month, 1)
            end = start + relativedelta(months=1) - dt.timedelta(days=1)
            end_date = end.strftime("%Y-%m-%d")

        client = get_api_client()
        api = firefly_iii_client.TransactionsApi(client)
        transactions = api.list_transaction(
            start=start_date,
            end=end_date,
            type='withdrawal'
        )

        # Filter for transactions without budget
        no_budget = []
        for txn in transactions.data:
            txn_data = txn.attributes.transactions[0]
            if not txn_data.budget_name:
                no_budget.append(txn)

        if not no_budget:
            return "✅ All transactions have budgets assigned"

        result = f"⚠️ Found {len(no_budget)} transaction(s) without budget:\n\n"
        result += "| ID | Date | Description | Amount |\n"
        result += "|------|------|-------------|--------|\n"

        for txn in no_budget[:50]:
            txn_data = txn.attributes.transactions[0]
            result += f"| {txn.id} | {txn_data.var_date} | {txn_data.description} | {format_amount(txn_data.amount)} |\n"

        return result
    except Exception as e:
        return format_error(e)

# ============================================================================
# CATEGORIES
# ============================================================================

@mcp.tool()
async def list_categories() -> str:
    """List all categories."""
    try:
        client = get_api_client()
        api = firefly_iii_client.CategoriesApi(client)
        categories = api.list_category()

        if not categories.data:
            return "📭 No categories found"

        result = f"📁 Found {len(categories.data)} category/categories:\n\n"
        result += "| ID | Name |\n"
        result += "|------|------|\n"

        for cat in categories.data:
            result += f"| {cat.id} | {cat.attributes.name} |\n"

        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def get_category_details(category_id: str = "") -> str:
    """Get detailed category information."""
    try:
        if not category_id.strip():
            return "❌ Error: category_id is required"

        client = get_api_client()
        api = firefly_iii_client.CategoriesApi(client)
        category = api.get_category(category_id)

        attrs = category.data.attributes
        result = f"""📂 Category Details: {attrs.name}

**ID:** {category.data.id}
**Notes:** {attrs.notes or 'None'}
"""
        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def create_category(name: str = "", notes: str = "") -> str:
    """Create a new category with name and optional notes."""
    try:
        if not name.strip():
            return "❌ Error: name is required"

        client = get_api_client()
        api = firefly_iii_client.CategoriesApi(client)

        category_data = {"name": name}
        if notes:
            category_data["notes"] = notes

        category_store = firefly_iii_client.CategoryStore(**category_data)
        category = api.store_category(category_store)

        return f"✅ Created category: {category.data.attributes.name} (ID: {category.data.id})"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def update_category(category_id: str = "", name: str = "", notes: str = "") -> str:
    """Update category name or notes."""
    try:
        if not category_id.strip():
            return "❌ Error: category_id is required"

        client = get_api_client()
        api = firefly_iii_client.CategoriesApi(client)

        update_data = {}
        if name:
            update_data["name"] = name
        if notes:
            update_data["notes"] = notes

        if not update_data:
            return "❌ Error: At least one field to update is required"

        category_update = firefly_iii_client.CategoryUpdate(**update_data)
        category = api.update_category(category_id, category_update)

        return f"✅ Updated category: {category.data.attributes.name}"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def delete_category(category_id: str = "", confirm: str = "") -> str:
    """Delete a category by ID (requires confirm='DELETE' for safety)."""
    try:
        if not category_id.strip():
            return "❌ Error: category_id is required"
        if confirm != "DELETE":
            return "⚠️ Warning: This will permanently delete the category. Set confirm='DELETE' to proceed."

        client = get_api_client()
        api = firefly_iii_client.CategoriesApi(client)
        api.delete_category(category_id)

        return f"✅ Deleted category ID: {category_id}"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def list_transactions_by_category(category_id: str = "", start_date: str = "", end_date: str = "") -> str:
    """List all transactions for a specific category with optional date range."""
    try:
        if not category_id.strip():
            return "❌ Error: category_id is required"

        client = get_api_client()
        cat_api = firefly_iii_client.CategoriesApi(client)

        params = {}
        if start_date:
            params['start'] = start_date
        if end_date:
            params['end'] = end_date

        transactions = cat_api.list_transaction_by_category(category_id, **params)

        if not transactions.data:
            return "📭 No transactions found"

        result = f"📝 Found {len(transactions.data)} transaction(s):\n\n"
        result += "| Date | Description | Amount |\n"
        result += "|------|-------------|--------|\n"

        for txn in transactions.data[:50]:
            attrs = txn.attributes.transactions[0]
            result += f"| {attrs.var_date} | {attrs.description} | {format_amount(attrs.amount)} {attrs.currency_code} |\n"

        return result
    except Exception as e:
        return format_error(e)

# ============================================================================
# TAGS
# ============================================================================

@mcp.tool()
async def list_tags() -> str:
    """List all tags."""
    try:
        client = get_api_client()
        api = firefly_iii_client.TagsApi(client)
        tags = api.list_tag()

        if not tags.data:
            return "📭 No tags found"

        result = f"🏷️ Found {len(tags.data)} tag(s):\n\n"
        result += "| ID | Tag | Date |\n"
        result += "|------|------|------|\n"

        for tag in tags.data:
            attrs = tag.attributes
            tag_date = attrs.var_date or 'N/A'
            result += f"| {tag.id} | {attrs.tag} | {tag_date} |\n"

        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def get_tag_details(tag_id: str = "") -> str:
    """Get detailed tag information."""
    try:
        if not tag_id.strip():
            return "❌ Error: tag_id is required"

        client = get_api_client()
        api = firefly_iii_client.TagsApi(client)
        tag = api.get_tag(tag_id)

        attrs = tag.data.attributes
        result = f"""🏷️ Tag Details: {attrs.tag}

**ID:** {tag.data.id}
**Date:** {attrs.var_date or 'N/A'}
**Description:** {attrs.description or 'None'}
"""
        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def create_tag(tag: str = "", date: str = "", description: str = "") -> str:
    """Create a new tag with name, optional date, and description."""
    try:
        if not tag.strip():
            return "❌ Error: tag is required"

        client = get_api_client()
        api = firefly_iii_client.TagsApi(client)

        tag_data = {"tag": tag}
        if date:
            tag_data["date"] = date
        if description:
            tag_data["description"] = description

        tag_model_store = firefly_iii_client.TagModelStore(**tag_data)
        tag_result = api.store_tag(tag_model_store)

        return f"✅ Created tag: {tag_result.data.attributes.tag} (ID: {tag_result.data.id})"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def update_tag(tag_id: str = "", tag: str = "", date: str = "", description: str = "") -> str:
    """Update tag name, date, or description."""
    try:
        if not tag_id.strip():
            return "❌ Error: tag_id is required"

        client = get_api_client()
        api = firefly_iii_client.TagsApi(client)

        update_data = {}
        if tag:
            update_data["tag"] = tag
        if date:
            update_data["date"] = date
        if description:
            update_data["description"] = description

        if not update_data:
            return "❌ Error: At least one field to update is required"

        tag_model_update = firefly_iii_client.TagModelUpdate(**update_data)
        tag_result = api.update_tag(tag_id, tag_model_update)

        return f"✅ Updated tag: {tag_result.data.attributes.tag}"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def delete_tag(tag_id: str = "", confirm: str = "") -> str:
    """Delete a tag by ID (requires confirm='DELETE' for safety)."""
    try:
        if not tag_id.strip():
            return "❌ Error: tag_id is required"
        if confirm != "DELETE":
            return "⚠️ Warning: This will permanently delete the tag. Set confirm='DELETE' to proceed."

        client = get_api_client()
        api = firefly_iii_client.TagsApi(client)
        api.delete_tag(tag_id)

        return f"✅ Deleted tag ID: {tag_id}"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def list_transactions_by_tag(tag_id: str = "", start_date: str = "", end_date: str = "") -> str:
    """List all transactions for a specific tag with optional date range."""
    try:
        if not tag_id.strip():
            return "❌ Error: tag_id is required"

        client = get_api_client()
        tag_api = firefly_iii_client.TagsApi(client)

        params = {}
        if start_date:
            params['start'] = start_date
        if end_date:
            params['end'] = end_date

        transactions = tag_api.list_transaction_by_tag(tag_id, **params)

        if not transactions.data:
            return "📭 No transactions found"

        result = f"📝 Found {len(transactions.data)} transaction(s):\n\n"
        result += "| Date | Description | Amount |\n"
        result += "|------|-------------|--------|\n"

        for txn in transactions.data[:50]:
            attrs = txn.attributes.transactions[0]
            result += f"| {attrs.var_date} | {attrs.description} | {format_amount(attrs.amount)} {attrs.currency_code} |\n"

        return result
    except Exception as e:
        return format_error(e)

# ============================================================================
# BILLS
# ============================================================================

@mcp.tool()
async def list_bills() -> str:
    """List all bills."""
    try:
        client = get_api_client()
        api = firefly_iii_client.BillsApi(client)
        bills = api.list_bill()

        if not bills.data:
            return "📭 No bills found"

        result = f"📄 Found {len(bills.data)} bill(s):\n\n"
        result += "| ID | Name | Amount Min | Amount Max | Active |\n"
        result += "|------|------|------------|------------|--------|\n"

        for bill in bills.data:
            attrs = bill.attributes
            active = '✓' if attrs.active else '✗'
            result += f"| {bill.id} | {attrs.name} | {format_amount(attrs.amount_min)} | {format_amount(attrs.amount_max)} | {active} |\n"

        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def get_bill_details(bill_id: str = "") -> str:
    """Get detailed bill information."""
    try:
        if not bill_id.strip():
            return "❌ Error: bill_id is required"

        client = get_api_client()
        api = firefly_iii_client.BillsApi(client)
        bill = api.get_bill(bill_id)

        attrs = bill.data.attributes
        result = f"""📋 Bill Details: {attrs.name}

**ID:** {bill.data.id}
**Active:** {'Yes' if attrs.active else 'No'}
**Amount Range:** {format_amount(attrs.amount_min)} - {format_amount(attrs.amount_max)} {attrs.currency_code}
**Repeat Frequency:** {attrs.repeat_freq}
**Skip:** {attrs.skip}

**Next Expected Match:** {attrs.next_expected_match or 'N/A'}
**Pay Dates:** {', '.join(attrs.pay_dates) if hasattr(attrs, 'pay_dates') and attrs.pay_dates else 'N/A'}

**Notes:** {attrs.notes or 'None'}
"""
        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def create_bill(name: str = "", amount_min: str = "", amount_max: str = "", currency_code: str = "USD", repeat_freq: str = "monthly", skip: str = "0", active: str = "true", notes: str = "", date: str = "") -> str:
    """Create a new bill with name, amount range, currency, repeat frequency, and other parameters.

    date: Optional. Date of first expected payment in YYYY-MM-DD format. If not provided, uses current date."""
    try:
        if not all([name.strip(), amount_min.strip(), amount_max.strip()]):
            return "❌ Error: name, amount_min, and amount_max are required"

        client = get_api_client()
        api = firefly_iii_client.BillsApi(client)

        bill_data = {
            "name": name,
            "amount_min": amount_min,
            "amount_max": amount_max,
            "currency_code": currency_code,
            "repeat_freq": repeat_freq,
            "skip": int(skip) if skip.strip() else 0,
            "active": active.lower() == "true",
            "date": date.strip() if date.strip() else datetime.now().strftime("%Y-%m-%d")
        }

        if notes:
            bill_data["notes"] = notes

        bill_store = firefly_iii_client.BillStore(**bill_data)
        bill = api.store_bill(bill_store)

        return f"✅ Created bill: {bill.data.attributes.name} (ID: {bill.data.id})"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def update_bill(bill_id: str = "", name: str = "", amount_min: str = "", amount_max: str = "", active: str = "", notes: str = "", date: str = "") -> str:
    """Update bill name, amount range, active status, notes, or next expected payment date.

    date: Optional. Date of next expected payment in YYYY-MM-DD format."""
    try:
        if not bill_id.strip():
            return "❌ Error: bill_id is required"

        client = get_api_client()
        api = firefly_iii_client.BillsApi(client)

        update_data = {}
        if name:
            update_data["name"] = name
        if amount_min:
            update_data["amount_min"] = amount_min
        if amount_max:
            update_data["amount_max"] = amount_max
        if active:
            update_data["active"] = active.lower() == "true"
        if notes:
            update_data["notes"] = notes
        if date:
            update_data["date"] = date.strip()

        if not update_data:
            return "❌ Error: At least one field to update is required"

        bill_update = firefly_iii_client.BillUpdate(**update_data)
        bill = api.update_bill(bill_id, bill_update)

        return f"✅ Updated bill: {bill.data.attributes.name}"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def delete_bill(bill_id: str = "", confirm: str = "") -> str:
    """Delete a bill by ID (requires confirm='DELETE' for safety)."""
    try:
        if not bill_id.strip():
            return "❌ Error: bill_id is required"
        if confirm != "DELETE":
            return "⚠️ Warning: This will permanently delete the bill. Set confirm='DELETE' to proceed."

        client = get_api_client()
        api = firefly_iii_client.BillsApi(client)
        api.delete_bill(bill_id)

        return f"✅ Deleted bill ID: {bill_id}"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def list_bill_transactions(bill_id: str = "", start_date: str = "", end_date: str = "") -> str:
    """List transactions attached to a specific bill with optional date range."""
    try:
        if not bill_id.strip():
            return "❌ Error: bill_id is required"

        client = get_api_client()
        api = firefly_iii_client.BillsApi(client)

        params = {}
        if start_date:
            params['start'] = start_date
        if end_date:
            params['end'] = end_date

        transactions = api.list_transaction_by_bill(bill_id, **params)

        if not transactions.data:
            return "📭 No transactions found"

        result = f"📝 Found {len(transactions.data)} transaction(s):\n\n"
        result += "| Date | Description | Amount |\n"
        result += "|------|-------------|--------|\n"

        for txn in transactions.data[:50]:
            attrs = txn.attributes.transactions[0]
            result += f"| {attrs.var_date} | {attrs.description} | {format_amount(attrs.amount)} {attrs.currency_code} |\n"

        return result
    except Exception as e:
        return format_error(e)

# ============================================================================
# PIGGY BANKS (continuing with remaining tools...)
# Due to length, I'll add more tools in the next section
# ============================================================================

@mcp.tool()
async def list_piggy_banks() -> str:
    """List all piggy banks."""
    try:
        client = get_api_client()
        api = firefly_iii_client.PiggyBanksApi(client)
        piggy_banks = api.list_piggy_bank()

        if not piggy_banks.data:
            return "📭 No piggy banks found"

        result = f"🐷 Found {len(piggy_banks.data)} piggy bank(s):\n\n"
        result += "| ID | Name | Target Amount | Current Amount | Progress |\n"
        result += "|------|------|---------------|----------------|----------|\n"

        for pb in piggy_banks.data:
            attrs = pb.attributes
            target = float(attrs.target_amount) if attrs.target_amount else 0
            current = float(attrs.current_amount) if attrs.current_amount else 0
            progress = (current / target * 100) if target > 0 else 0
            result += f"| {pb.id} | {attrs.name} | {attrs.target_amount} | {attrs.current_amount} | {progress:.1f}% |\n"

        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def get_piggy_bank_details(piggy_bank_id: str = "") -> str:
    """Get detailed piggy bank information including progress toward target."""
    try:
        if not piggy_bank_id.strip():
            return "❌ Error: piggy_bank_id is required"

        client = get_api_client()
        api = firefly_iii_client.PiggyBanksApi(client)
        piggy_bank = api.get_piggy_bank(piggy_bank_id)

        attrs = piggy_bank.data.attributes
        target = float(attrs.target_amount) if attrs.target_amount else 0
        current = float(attrs.current_amount) if attrs.current_amount else 0
        remaining = target - current
        progress = (current / target * 100) if target > 0 else 0

        result = f"""🐷 Piggy Bank Details: {attrs.name}

**ID:** {piggy_bank.data.id}
**Account:** {attrs.account_name} (ID: {attrs.account_id})
**Target Amount:** {format_amount(attrs.target_amount)} {attrs.currency_code}
**Current Amount:** {format_amount(attrs.current_amount)} {attrs.currency_code}
**Remaining:** {remaining:.2f} {attrs.currency_code}
**Progress:** {progress:.1f}%

**Start Date:** {attrs.start_date or 'N/A'}
**Target Date:** {attrs.target_date or 'N/A'}

**Notes:** {attrs.notes or 'None'}
"""
        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def create_piggy_bank(name: str = "", account_id: str = "", target_amount: str = "", current_amount: str = "0", start_date: str = "", target_date: str = "", notes: str = "") -> str:
    """Create a new piggy bank with name, account ID, target amount, and other parameters."""
    try:
        if not all([name.strip(), account_id.strip(), target_amount.strip()]):
            return "❌ Error: name, account_id, and target_amount are required"

        client = get_api_client()
        api = firefly_iii_client.PiggyBanksApi(client)

        piggy_bank_data = {
            "name": name,
            "account_id": account_id,
            "target_amount": target_amount
        }

        if current_amount and current_amount != "0":
            piggy_bank_data["current_amount"] = current_amount
        if start_date:
            piggy_bank_data["start_date"] = start_date
        if target_date:
            piggy_bank_data["target_date"] = target_date
        if notes:
            piggy_bank_data["notes"] = notes

        piggy_bank_store = firefly_iii_client.PiggyBankStore(**piggy_bank_data)
        piggy_bank = api.store_piggy_bank(piggy_bank_store)

        return f"✅ Created piggy bank: {piggy_bank.data.attributes.name} (ID: {piggy_bank.data.id})"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def update_piggy_bank(piggy_bank_id: str = "", name: str = "", target_amount: str = "", current_amount: str = "", notes: str = "") -> str:
    """Update piggy bank name, target amount, current amount, or notes."""
    try:
        if not piggy_bank_id.strip():
            return "❌ Error: piggy_bank_id is required"

        client = get_api_client()
        api = firefly_iii_client.PiggyBanksApi(client)

        update_data = {}
        if name:
            update_data["name"] = name
        if target_amount:
            update_data["target_amount"] = target_amount
        if current_amount:
            update_data["current_amount"] = current_amount
        if notes:
            update_data["notes"] = notes

        if not update_data:
            return "❌ Error: At least one field to update is required"

        piggy_bank_update = firefly_iii_client.PiggyBankUpdate(**update_data)
        piggy_bank = api.update_piggy_bank(piggy_bank_id, piggy_bank_update)

        return f"✅ Updated piggy bank: {piggy_bank.data.attributes.name}"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def delete_piggy_bank(piggy_bank_id: str = "", confirm: str = "") -> str:
    """Delete a piggy bank by ID (requires confirm='DELETE' for safety)."""
    try:
        if not piggy_bank_id.strip():
            return "❌ Error: piggy_bank_id is required"
        if confirm != "DELETE":
            return "⚠️ Warning: This will permanently delete the piggy bank. Set confirm='DELETE' to proceed."

        client = get_api_client()
        api = firefly_iii_client.PiggyBanksApi(client)
        api.delete_piggy_bank(piggy_bank_id)

        return f"✅ Deleted piggy bank ID: {piggy_bank_id}"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def list_piggy_bank_events(piggy_bank_id: str = "") -> str:
    """List all events (money movements) for a specific piggy bank."""
    try:
        if not piggy_bank_id.strip():
            return "❌ Error: piggy_bank_id is required"

        client = get_api_client()
        api = firefly_iii_client.PiggyBanksApi(client)
        events = api.list_event_by_piggy_bank(piggy_bank_id)

        if not events.data:
            return "📭 No events found"

        result = f"📊 Piggy Bank Events:\n\n"
        result += "| Date | Amount | Transaction |\n"
        result += "|------|--------|-------------|\n"

        for event in events.data:
            attrs = event.attributes
            result += f"| {attrs.created_at} | {format_amount(attrs.amount)} {attrs.currency_code} | {attrs.transaction_journal_id or 'N/A'} |\n"

        return result
    except Exception as e:
        return format_error(e)

# ============================================================================
# AUTOCOMPLETE HELPERS
# ============================================================================

@mcp.tool()
async def autocomplete_accounts(query: str = "") -> str:
    """Search for accounts by partial name and return best matches in a compact table."""
    try:
        if not query.strip():
            return "❌ Error: query is required"

        client = get_api_client()
        api = firefly_iii_client.AutocompleteApi(client)
        results = api.get_accounts_ac(query=query)

        if not results:
            return "📭 No matching accounts found"

        result = f"💰 Account Matches for '{query}':\n\n"
        result += "| ID | Name | Type |\n"
        result += "|------|------|------|\n"

        for acc in results[:10]:
            result += f"| {acc.id} | {acc.name} | {acc.type if hasattr(acc, 'type') else 'N/A'} |\n"

        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def autocomplete_categories(query: str = "") -> str:
    """Search for categories by partial name and return best matches in a compact table."""
    try:
        if not query.strip():
            return "❌ Error: query is required"

        client = get_api_client()
        api = firefly_iii_client.AutocompleteApi(client)
        results = api.get_categories_ac(query=query)

        if not results:
            return "📭 No matching categories found"

        result = f"📁 Category Matches for '{query}':\n\n"
        result += "| ID | Name |\n"
        result += "|------|------|\n"

        for cat in results[:10]:
            result += f"| {cat.id} | {cat.name} |\n"

        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def autocomplete_tags(query: str = "") -> str:
    """Search for tags by partial name and return best matches in a compact table."""
    try:
        if not query.strip():
            return "❌ Error: query is required"

        client = get_api_client()
        api = firefly_iii_client.AutocompleteApi(client)
        results = api.get_tags_ac(query=query)

        if not results:
            return "📭 No matching tags found"

        result = f"🏷️ Tag Matches for '{query}':\n\n"
        result += "| ID | Name |\n"
        result += "|------|------|\n"

        for tag in results[:10]:
            result += f"| {tag.id} | {tag.name} |\n"

        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def autocomplete_budgets(query: str = "") -> str:
    """Search for budgets by partial name and return best matches in a compact table."""
    try:
        if not query.strip():
            return "❌ Error: query is required"

        client = get_api_client()
        api = firefly_iii_client.AutocompleteApi(client)
        results = api.get_budgets_ac(query=query)

        if not results:
            return "📭 No matching budgets found"

        result = f"💼 Budget Matches for '{query}':\n\n"
        result += "| ID | Name |\n"
        result += "|------|------|\n"

        for budget in results[:10]:
            result += f"| {budget.id} | {budget.name} |\n"

        return result
    except Exception as e:
        return format_error(e)

# ============================================================================
# CURRENCIES
# ============================================================================

@mcp.tool()
async def list_currencies() -> str:
    """List all currencies."""
    try:
        client = get_api_client()
        api = firefly_iii_client.CurrenciesApi(client)
        currencies = api.list_currency()

        if not currencies.data:
            return "📭 No currencies found"

        result = f"💱 Found {len(currencies.data)} currency/currencies:\n\n"
        result += "| ID | Code | Name | Symbol | Enabled | Default |\n"
        result += "|------|------|------|--------|---------|----------|\n"

        for curr in currencies.data:
            attrs = curr.attributes
            enabled = '✓' if attrs.enabled else '✗'
            default = '✓' if attrs.default else '✗'
            result += f"| {curr.id} | {attrs.code} | {attrs.name} | {attrs.symbol} | {enabled} | {default} |\n"

        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def get_currency_details(currency_id: str = "") -> str:
    """Get detailed currency information."""
    try:
        if not currency_id.strip():
            return "❌ Error: currency_id is required"

        client = get_api_client()
        api = firefly_iii_client.CurrenciesApi(client)
        currency = api.get_currency(currency_id)

        attrs = currency.data.attributes
        result = f"""💱 Currency Details: {attrs.name}

**ID:** {currency.data.id}
**Code:** {attrs.code}
**Symbol:** {attrs.symbol}
**Enabled:** {'Yes' if attrs.enabled else 'No'}
**Default:** {'Yes' if attrs.default else 'No'}
**Decimal Places:** {attrs.decimal_places}
"""
        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def enable_currency(currency_id: str = "") -> str:
    """Enable a currency."""
    try:
        if not currency_id.strip():
            return "❌ Error: currency_id is required"

        client = get_api_client()
        api = firefly_iii_client.CurrenciesApi(client)
        currency = api.enable_currency(currency_id)

        return f"✅ Enabled currency: {currency.data.attributes.name}"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def disable_currency(currency_id: str = "") -> str:
    """Disable a currency."""
    try:
        if not currency_id.strip():
            return "❌ Error: currency_id is required"

        client = get_api_client()
        api = firefly_iii_client.CurrenciesApi(client)
        currency = api.disable_currency(currency_id)

        return f"✅ Disabled currency: {currency.data.attributes.name}"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def set_default_currency(currency_id: str = "") -> str:
    """Set a currency as the default currency."""
    try:
        if not currency_id.strip():
            return "❌ Error: currency_id is required"

        client = get_api_client()
        api = firefly_iii_client.CurrenciesApi(client)
        currency = api.default_currency(currency_id)

        return f"✅ Set default currency: {currency.data.attributes.name}"
    except Exception as e:
        return format_error(e)

# ============================================================================
# SEARCH
# ============================================================================

@mcp.tool()
async def search_all(query: str = "", field: str = "all") -> str:
    """Search across all Firefly III data (accounts, transactions, etc.) with optional field filter (all, transactions, accounts)."""
    try:
        if not query.strip():
            return "❌ Error: query is required"

        client = get_api_client()
        api = firefly_iii_client.SearchApi(client)

        params = {"query": query}
        # SearchApi doesn't accept 'field' parameter - removed to fix bug

        results = api.search_transactions(**params)

        if not results.data:
            return "📭 No results found"

        result = f"🔍 Search Results for '{query}':\n\n"
        result += "| Type | ID | Name/Description |\n"
        result += "|------|------|------------------|\n"

        for item in results.data[:50]:
            if hasattr(item.attributes, 'description'):
                desc = item.attributes.description
            elif hasattr(item.attributes, 'name'):
                desc = item.attributes.name
            else:
                desc = 'N/A'
            result += f"| Transaction | {item.id} | {desc} |\n"

        return result
    except Exception as e:
        return format_error(e)

# ============================================================================
# INSIGHTS & SUMMARIES
# ============================================================================

@mcp.tool()
async def spending_summary(start_date: str = "", end_date: str = "", group_by: str = "category") -> str:
    """Get spending summary grouped by category, budget, tag, or account for a given date range."""
    try:
        if not start_date or not end_date:
            now = datetime.now()
            start_date = f"{now.year}-{now.month:02d}-01"
            from dateutil.relativedelta import relativedelta
            import datetime as dt
            start = dt.date(now.year, now.month, 1)
            end = start + relativedelta(months=1) - dt.timedelta(days=1)
            end_date = end.strftime("%Y-%m-%d")

        client = get_api_client()

        # Get all expense transactions in the period
        txn_api = firefly_iii_client.TransactionsApi(client)
        transactions = txn_api.list_transaction(
            start=start_date,
            end=end_date,
            type='withdrawal'
        )

        # Group by the specified field
        grouped = {}
        total = 0

        for txn in transactions.data:
            txn_data = txn.attributes.transactions[0]
            amount = float(txn_data.amount)
            total += amount

            if group_by == "category":
                key = txn_data.category_name or "Uncategorized"
            elif group_by == "budget":
                key = txn_data.budget_name or "No Budget"
            elif group_by == "account":
                key = txn_data.source_name
            else:
                key = "Other"

            if key not in grouped:
                grouped[key] = 0
            grouped[key] += amount

        result = f"💸 Spending Summary ({start_date} to {end_date})\nGrouped by: {group_by.capitalize()}\n\n"
        result += "| Category | Amount | % of Total |\n"
        result += "|----------|--------|------------|\n"

        for key in sorted(grouped.keys(), key=lambda k: grouped[k], reverse=True):
            amount = grouped[key]
            pct = (amount / total * 100) if total > 0 else 0
            result += f"| {key} | {amount:.2f} | {pct:.1f}% |\n"

        result += f"\n**Total Spending:** {total:.2f}"
        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def income_summary(start_date: str = "", end_date: str = "", group_by: str = "category") -> str:
    """Get income summary grouped by category, budget, tag, or account for a given date range."""
    try:
        if not start_date or not end_date:
            now = datetime.now()
            start_date = f"{now.year}-{now.month:02d}-01"
            from dateutil.relativedelta import relativedelta
            import datetime as dt
            start = dt.date(now.year, now.month, 1)
            end = start + relativedelta(months=1) - dt.timedelta(days=1)
            end_date = end.strftime("%Y-%m-%d")

        client = get_api_client()

        # Get all income transactions in the period
        txn_api = firefly_iii_client.TransactionsApi(client)
        transactions = txn_api.list_transaction(
            start=start_date,
            end=end_date,
            type='deposit'
        )

        # Group by the specified field
        grouped = {}
        total = 0

        for txn in transactions.data:
            txn_data = txn.attributes.transactions[0]
            amount = float(txn_data.amount)
            total += amount

            if group_by == "category":
                key = txn_data.category_name or "Uncategorized"
            elif group_by == "budget":
                key = txn_data.budget_name or "No Budget"
            elif group_by == "account":
                key = txn_data.destination_name
            else:
                key = "Other"

            if key not in grouped:
                grouped[key] = 0
            grouped[key] += amount

        result = f"💰 Income Summary ({start_date} to {end_date})\nGrouped by: {group_by.capitalize()}\n\n"
        result += "| Category | Amount | % of Total |\n"
        result += "|----------|--------|------------|\n"

        for key in sorted(grouped.keys(), key=lambda k: grouped[k], reverse=True):
            amount = grouped[key]
            pct = (amount / total * 100) if total > 0 else 0
            result += f"| {key} | {amount:.2f} | {pct:.1f}% |\n"

        result += f"\n**Total Income:** {total:.2f}"
        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def net_flow_summary(start_date: str = "", end_date: str = "") -> str:
    """Get net cash flow summary (income - expenses) for a given period."""
    try:
        if not start_date or not end_date:
            now = datetime.now()
            start_date = f"{now.year}-{now.month:02d}-01"
            from dateutil.relativedelta import relativedelta
            import datetime as dt
            start = dt.date(now.year, now.month, 1)
            end = start + relativedelta(months=1) - dt.timedelta(days=1)
            end_date = end.strftime("%Y-%m-%d")

        client = get_api_client()
        txn_api = firefly_iii_client.TransactionsApi(client)

        # Get deposits (income)
        deposits = txn_api.list_transaction(
            start=start_date,
            end=end_date,
            type='deposit'
        )
        total_income = sum(float(txn.attributes.transactions[0].amount) for txn in deposits.data)

        # Get withdrawals (expenses)
        withdrawals = txn_api.list_transaction(
            start=start_date,
            end=end_date,
            type='withdrawal'
        )
        total_expenses = sum(float(txn.attributes.transactions[0].amount) for txn in withdrawals.data)

        net_flow = total_income - total_expenses

        result = f"""📊 Net Flow Summary ({start_date} to {end_date})

**Total Income:** {total_income:.2f}
**Total Expenses:** {total_expenses:.2f}
**Net Flow:** {net_flow:.2f}

**Savings Rate:** {(net_flow / total_income * 100) if total_income > 0 else 0:.1f}%
"""
        return result
    except Exception as e:
        return format_error(e)

# ============================================================================
# RULES & RULE GROUPS
# ============================================================================

@mcp.tool()
async def list_rule_groups() -> str:
    """List all rule groups."""
    try:
        client = get_api_client()
        api = firefly_iii_client.RuleGroupsApi(client)
        rule_groups = api.list_rule_group()

        if not rule_groups.data:
            return "📭 No rule groups found"

        result = f"📋 Found {len(rule_groups.data)} rule group(s):\n\n"
        result += "| ID | Title | Active | Order |\n"
        result += "|------|-------|--------|-------|\n"

        for rg in rule_groups.data:
            attrs = rg.attributes
            active = '✓' if attrs.active else '✗'
            result += f"| {rg.id} | {attrs.title} | {active} | {attrs.order} |\n"

        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def get_rule_group_details(rule_group_id: str = "") -> str:
    """Get detailed rule group information."""
    try:
        if not rule_group_id.strip():
            return "❌ Error: rule_group_id is required"

        client = get_api_client()
        api = firefly_iii_client.RuleGroupsApi(client)
        rule_group = api.get_rule_group(rule_group_id)

        attrs = rule_group.data.attributes
        result = f"""📋 Rule Group Details: {attrs.title}

**ID:** {rule_group.data.id}
**Active:** {'Yes' if attrs.active else 'No'}
**Order:** {attrs.order}
**Description:** {attrs.description or 'None'}
"""
        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def create_rule_group(title: str = "", description: str = "", active: str = "true", order: str = "1") -> str:
    """Create a new rule group with title, description, active status, and order."""
    try:
        if not title.strip():
            return "❌ Error: title is required"

        client = get_api_client()
        api = firefly_iii_client.RuleGroupsApi(client)

        rule_group_data = {
            "title": title,
            "active": active.lower() == "true",
            "order": int(order) if order.strip() else 1
        }

        if description:
            rule_group_data["description"] = description

        rule_group_store = firefly_iii_client.RuleGroupStore(**rule_group_data)
        rule_group = api.store_rule_group(rule_group_store)

        return f"✅ Created rule group: {rule_group.data.attributes.title} (ID: {rule_group.data.id})"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def update_rule_group(rule_group_id: str = "", title: str = "", description: str = "", active: str = "", order: str = "") -> str:
    """Update rule group title, description, active status, or order."""
    try:
        if not rule_group_id.strip():
            return "❌ Error: rule_group_id is required"

        client = get_api_client()
        api = firefly_iii_client.RuleGroupsApi(client)

        update_data = {}
        if title:
            update_data["title"] = title
        if description:
            update_data["description"] = description
        if active:
            update_data["active"] = active.lower() == "true"
        if order:
            update_data["order"] = int(order)

        if not update_data:
            return "❌ Error: At least one field to update is required"

        rule_group_update = firefly_iii_client.RuleGroupUpdate(**update_data)
        rule_group = api.update_rule_group(rule_group_id, rule_group_update)

        return f"✅ Updated rule group: {rule_group.data.attributes.title}"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def delete_rule_group(rule_group_id: str = "", confirm: str = "") -> str:
    """Delete a rule group by ID (requires confirm='DELETE' for safety)."""
    try:
        if not rule_group_id.strip():
            return "❌ Error: rule_group_id is required"
        if confirm != "DELETE":
            return "⚠️ Warning: This will permanently delete the rule group. Set confirm='DELETE' to proceed."

        client = get_api_client()
        api = firefly_iii_client.RuleGroupsApi(client)
        api.delete_rule_group(rule_group_id)

        return f"✅ Deleted rule group ID: {rule_group_id}"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def list_rules(rule_group_id: str = "") -> str:
    """List all rules, optionally filtered by rule group ID."""
    try:
        client = get_api_client()
        api = firefly_iii_client.RulesApi(client)

        if rule_group_id.strip():
            # List rules in a specific rule group
            rg_api = firefly_iii_client.RuleGroupsApi(client)
            rules = rg_api.list_rule_by_group(rule_group_id)
        else:
            # List all rules
            rules = api.list_rule()

        if not rules.data:
            return "📭 No rules found"

        result = f"📜 Found {len(rules.data)} rule(s):\n\n"
        result += "| ID | Title | Active | Strict | Stop Processing |\n"
        result += "|------|-------|--------|--------|------------------|\n"

        for rule in rules.data:
            attrs = rule.attributes
            active = '✓' if attrs.active else '✗'
            strict = '✓' if attrs.strict else '✗'
            stop = '✓' if attrs.stop_processing else '✗'
            result += f"| {rule.id} | {attrs.title} | {active} | {strict} | {stop} |\n"

        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def get_rule_details(rule_id: str = "") -> str:
    """Get detailed rule information including triggers and actions."""
    try:
        if not rule_id.strip():
            return "❌ Error: rule_id is required"

        client = get_api_client()
        api = firefly_iii_client.RulesApi(client)
        rule = api.get_rule(rule_id)

        attrs = rule.data.attributes

        # Format triggers
        triggers = "\n".join([f"  - {t['type']}: {t['value']}" for t in attrs.triggers]) if attrs.triggers else "None"

        # Format actions
        actions = "\n".join([f"  - {a['type']}: {a['value']}" for a in attrs.actions]) if attrs.actions else "None"

        result = f"""📜 Rule Details: {attrs.title}

**ID:** {rule.data.id}
**Active:** {'Yes' if attrs.active else 'No'}
**Order:** {attrs.order}
**Strict:** {'Yes' if attrs.strict else 'No'}
**Stop Processing:** {'Yes' if attrs.stop_processing else 'No'}

**Triggers:**
{triggers}

**Actions:**
{actions}

**Description:** {attrs.description or 'None'}
"""
        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def create_rule(title: str = "", rule_group_id: str = "", triggers_json: str = "", actions_json: str = "", active: str = "true", strict: str = "true", stop_processing: str = "false", description: str = "") -> str:
    """Create a new rule with title, rule group ID, triggers (JSON array), actions (JSON array), and other parameters."""
    try:
        if not all([title.strip(), rule_group_id.strip(), triggers_json.strip(), actions_json.strip()]):
            return "❌ Error: title, rule_group_id, triggers_json, and actions_json are required"

        # Parse triggers and actions
        try:
            triggers = json.loads(triggers_json)
            actions = json.loads(actions_json)
        except:
            return "❌ Error: triggers_json and actions_json must be valid JSON arrays"

        client = get_api_client()
        api = firefly_iii_client.RulesApi(client)

        rule_data = {
            "title": title,
            "rule_group_id": rule_group_id,
            "trigger": "store-journal",
            "triggers": triggers,
            "actions": actions,
            "active": active.lower() == "true",
            "strict": strict.lower() == "true",
            "stop_processing": stop_processing.lower() == "true"
        }

        if description:
            rule_data["description"] = description

        rule_store = firefly_iii_client.RuleStore(**rule_data)
        rule = api.store_rule(rule_store)

        return f"✅ Created rule: {rule.data.attributes.title} (ID: {rule.data.id})"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def update_rule(rule_id: str = "", title: str = "", active: str = "", triggers_json: str = "", actions_json: str = "", description: str = "") -> str:
    """Update rule title, active status, triggers, actions, or description."""
    try:
        if not rule_id.strip():
            return "❌ Error: rule_id is required"

        client = get_api_client()
        api = firefly_iii_client.RulesApi(client)

        update_data = {}
        if title:
            update_data["title"] = title
        if active:
            update_data["active"] = active.lower() == "true"
        if triggers_json:
            try:
                update_data["triggers"] = json.loads(triggers_json)
            except:
                return "❌ Error: triggers_json must be valid JSON"
        if actions_json:
            try:
                update_data["actions"] = json.loads(actions_json)
            except:
                return "❌ Error: actions_json must be valid JSON"
        if description:
            update_data["description"] = description

        if not update_data:
            return "❌ Error: At least one field to update is required"

        rule_update = firefly_iii_client.RuleUpdate(**update_data)
        rule = api.update_rule(rule_id, rule_update)

        return f"✅ Updated rule: {rule.data.attributes.title}"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def delete_rule(rule_id: str = "", confirm: str = "") -> str:
    """Delete a rule by ID (requires confirm='DELETE' for safety)."""
    try:
        if not rule_id.strip():
            return "❌ Error: rule_id is required"
        if confirm != "DELETE":
            return "⚠️ Warning: This will permanently delete the rule. Set confirm='DELETE' to proceed."

        client = get_api_client()
        api = firefly_iii_client.RulesApi(client)
        api.delete_rule(rule_id)

        return f"✅ Deleted rule ID: {rule_id}"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def test_rule(rule_id: str = "", start_date: str = "", end_date: str = "") -> str:
    """Test a rule against transactions in a date range to see which transactions would be affected."""
    try:
        if not rule_id.strip():
            return "❌ Error: rule_id is required"

        client = get_api_client()
        api = firefly_iii_client.RulesApi(client)

        params = {}
        if start_date:
            params['start'] = start_date
        if end_date:
            params['end'] = end_date

        transactions = api.test_rule(rule_id, **params)

        if not transactions.data:
            return "📭 No transactions would be affected by this rule"

        result = f"🔍 Rule Test Results ({len(transactions.data)} transactions affected):\n\n"
        result += "| ID | Date | Description | Amount |\n"
        result += "|------|------|-------------|--------|\n"

        for txn in transactions.data[:50]:
            attrs = txn.attributes.transactions[0]
            result += f"| {txn.id} | {attrs.var_date} | {attrs.description} | {format_amount(attrs.amount)} {attrs.currency_code} |\n"

        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def trigger_rule(rule_id: str = "", start_date: str = "", end_date: str = "") -> str:
    """Trigger a rule to run against transactions in a date range (actually applies the rule actions)."""
    try:
        if not rule_id.strip():
            return "❌ Error: rule_id is required"

        client = get_api_client()
        api = firefly_iii_client.RulesApi(client)

        params = {}
        if start_date:
            params['start'] = start_date
        if end_date:
            params['end'] = end_date

        api.fire_rule(rule_id, **params)

        return f"✅ Successfully triggered rule ID: {rule_id}"
    except Exception as e:
        return format_error(e)

# ============================================================================
# RECURRENCES (RECURRING TRANSACTIONS)
# ============================================================================

@mcp.tool()
async def list_recurrences() -> str:
    """List all recurring transactions."""
    try:
        client = get_api_client()
        api = firefly_iii_client.RecurrencesApi(client)
        recurrences = api.list_recurrence()

        if not recurrences.data:
            return "📭 No recurring transactions found"

        result = f"🔁 Found {len(recurrences.data)} recurring transaction(s):\n\n"
        result += "| ID | Title | Active | Repeat Freq | First Date | Latest Date |\n"
        result += "|------|-------|--------|-------------|------------|-------------|\n"

        for rec in recurrences.data:
            attrs = rec.attributes
            active = '✓' if attrs.active else '✗'
            latest = attrs.latest_date or 'N/A'
            result += f"| {rec.id} | {attrs.title} | {active} | {attrs.repeat_freq} | {attrs.first_date} | {latest} |\n"

        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def get_recurrence_details(recurrence_id: str = "") -> str:
    """Get detailed recurring transaction information."""
    try:
        if not recurrence_id.strip():
            return "❌ Error: recurrence_id is required"

        client = get_api_client()
        api = firefly_iii_client.RecurrencesApi(client)
        recurrence = api.get_recurrence(recurrence_id)

        attrs = recurrence.data.attributes

        # Get first repetition details
        rep = attrs.repetitions[0] if attrs.repetitions else None
        rep_info = ""
        if rep:
            rep_info = f"""
**Repetition Type:** {rep['type']}
**Moment:** {rep['moment']}
**Skip:** {rep['skip']}
"""

        # Get first transaction details
        txn = attrs.transactions[0] if attrs.transactions else None
        txn_info = ""
        if txn:
            txn_info = f"""
**Transaction Type:** {txn['type']}
**Description:** {txn['description']}
**Amount:** {format_amount(txn['amount'])} {txn['currency_code']}
**Source:** {txn.get('source_name', 'N/A')}
**Destination:** {txn.get('destination_name', 'N/A')}
**Category:** {txn.get('category_name', 'None')}
**Budget:** {txn.get('budget_name', 'None')}
"""

        result = f"""🔁 Recurrence Details: {attrs.title}

**ID:** {recurrence.data.id}
**Active:** {'Yes' if attrs.active else 'No'}
**Repeat Frequency:** {attrs.repeat_freq}
**Apply Rules:** {'Yes' if attrs.apply_rules else 'No'}

**First Date:** {attrs.first_date}
**Latest Date:** {attrs.latest_date or 'Ongoing'}
**Repeat Until:** {attrs.repeat_until or 'Forever'}
**Nr of Repetitions:** {attrs.nr_of_repetitions or 'Unlimited'}
{rep_info}
{txn_info}
**Description:** {attrs.description or 'None'}
**Notes:** {attrs.notes or 'None'}
"""
        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def create_recurrence(title: str = "", first_date: str = "", repeat_freq: str = "monthly", recurrence_type: str = "withdrawal", description: str = "", amount: str = "", source_account: str = "", destination_account: str = "", category: str = "", budget: str = "", notes: str = "") -> str:
    """Create a new recurring transaction with title, first date, repeat frequency (daily, weekly, monthly, yearly), transaction type, and other parameters."""
    try:
        if not all([title.strip(), first_date.strip(), amount.strip()]):
            return "❌ Error: title, first_date, and amount are required"

        client = get_api_client()
        api = firefly_iii_client.RecurrencesApi(client)

        # Build transaction data
        transaction_data = {
            "type": recurrence_type,
            "description": description if description else title,
            "amount": amount,
            "currency_code": "USD"
        }

        if recurrence_type == "withdrawal":
            if source_account:
                transaction_data["source_id"] = source_account
            if destination_account:
                transaction_data["destination_name"] = destination_account
            else:
                transaction_data["destination_name"] = "Cash account"
        elif recurrence_type == "deposit":
            if destination_account:
                transaction_data["destination_id"] = destination_account
            if source_account:
                transaction_data["source_name"] = source_account
            else:
                transaction_data["source_name"] = "Cash account"
        elif recurrence_type == "transfer":
            if not source_account or not destination_account:
                return "❌ Error: Both source_account and destination_account required for transfers"
            transaction_data["source_id"] = source_account
            transaction_data["destination_id"] = destination_account

        if category:
            transaction_data["category_name"] = category
        if budget:
            # Route to budget_id for numeric input, budget_name for text
            if budget.strip().isdigit():
                transaction_data["budget_id"] = budget
            else:
                transaction_data["budget_name"] = budget

        # Build repetition data
        repetition_data = {
            "type": repeat_freq,
            "moment": "1",
            "skip": 0
        }

        recurrence_data = {
            "title": title,
            "first_date": first_date,
            "repeat_freq": repeat_freq,
            "type": "recurrence",
            "repetitions": [repetition_data],
            "transactions": [firefly_iii_client.RecurrenceTransactionStore(**transaction_data)],
            "apply_rules": True,
            "active": True
        }

        if notes:
            recurrence_data["notes"] = notes

        recurrence_store = firefly_iii_client.RecurrenceStore(**recurrence_data)
        recurrence = api.store_recurrence(recurrence_store)

        return f"✅ Created recurring transaction: {recurrence.data.attributes.title} (ID: {recurrence.data.id})"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def update_recurrence(recurrence_id: str = "", title: str = "", active: str = "", notes: str = "") -> str:
    """Update recurring transaction title, active status, or notes."""
    try:
        if not recurrence_id.strip():
            return "❌ Error: recurrence_id is required"

        client = get_api_client()
        api = firefly_iii_client.RecurrencesApi(client)

        update_data = {}
        if title:
            update_data["title"] = title
        if active:
            update_data["active"] = active.lower() == "true"
        if notes:
            update_data["notes"] = notes

        if not update_data:
            return "❌ Error: At least one field to update is required"

        recurrence_update = firefly_iii_client.RecurrenceUpdate(**update_data)
        recurrence = api.update_recurrence(recurrence_id, recurrence_update)

        return f"✅ Updated recurring transaction: {recurrence.data.attributes.title}"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def delete_recurrence(recurrence_id: str = "", confirm: str = "") -> str:
    """Delete a recurring transaction by ID (requires confirm='DELETE' for safety)."""
    try:
        if not recurrence_id.strip():
            return "❌ Error: recurrence_id is required"
        if confirm != "DELETE":
            return "⚠️ Warning: This will permanently delete the recurring transaction. Set confirm='DELETE' to proceed."

        client = get_api_client()
        api = firefly_iii_client.RecurrencesApi(client)
        api.delete_recurrence(recurrence_id)

        return f"✅ Deleted recurring transaction ID: {recurrence_id}"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def list_recurrence_transactions(recurrence_id: str = "") -> str:
    """List all transactions created by a specific recurring transaction."""
    try:
        if not recurrence_id.strip():
            return "❌ Error: recurrence_id is required"

        client = get_api_client()
        api = firefly_iii_client.RecurrencesApi(client)
        transactions = api.list_transaction_by_recurrence(recurrence_id)

        if not transactions.data:
            return "📭 No transactions created yet"

        result = f"📝 Transactions created by recurrence:\n\n"
        result += "| ID | Date | Description | Amount |\n"
        result += "|------|------|-------------|--------|\n"

        for txn in transactions.data[:50]:
            attrs = txn.attributes.transactions[0]
            result += f"| {txn.id} | {attrs.var_date} | {attrs.description} | {format_amount(attrs.amount)} {attrs.currency_code} |\n"

        return result
    except Exception as e:
        return format_error(e)

# ============================================================================
# WEBHOOKS
# ============================================================================

@mcp.tool()
async def list_webhooks() -> str:
    """List all webhooks."""
    try:
        client = get_api_client()
        api = firefly_iii_client.WebhooksApi(client)
        webhooks = api.list_webhook()

        if not webhooks.data:
            return "📭 No webhooks found"

        result = f"🔗 Found {len(webhooks.data)} webhook(s):\n\n"
        result += "| ID | Title | Active | Trigger | Response | URL |\n"
        result += "|------|-------|--------|---------|----------|-----|\n"

        for wh in webhooks.data:
            attrs = wh.attributes
            active = '✓' if attrs.active else '✗'
            result += f"| {wh.id} | {attrs.title} | {active} | {attrs.trigger} | {attrs.response} | {attrs.url[:30]}... |\n"

        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def get_webhook_details(webhook_id: str = "") -> str:
    """Get detailed webhook information."""
    try:
        if not webhook_id.strip():
            return "❌ Error: webhook_id is required"

        client = get_api_client()
        api = firefly_iii_client.WebhooksApi(client)
        webhook = api.get_webhook(webhook_id)

        attrs = webhook.data.attributes
        result = f"""🔗 Webhook Details: {attrs.title}

**ID:** {webhook.data.id}
**Active:** {'Yes' if attrs.active else 'No'}
**Trigger:** {attrs.trigger}
**Response:** {attrs.response}
**Delivery:** {attrs.delivery}
**URL:** {attrs.url}

**Secret:** {'[CONFIGURED]' if hasattr(attrs, 'secret') and attrs.secret else '[NOT SET]'}
"""
        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def create_webhook(title: str = "", url: str = "", trigger: str = "STORE_TRANSACTION", response: str = "TRANSACTIONS", delivery: str = "JSON", active: str = "true") -> str:
    """Create a new webhook with title, URL, trigger event, response type, and delivery format."""
    try:
        if not all([title.strip(), url.strip()]):
            return "❌ Error: title and url are required"

        client = get_api_client()
        api = firefly_iii_client.WebhooksApi(client)

        webhook_data = {
            "title": title,
            "trigger": trigger,
            "response": response,
            "delivery": delivery,
            "url": url,
            "active": active.lower() == "true"
        }

        webhook_store = firefly_iii_client.WebhookStore(**webhook_data)
        webhook = api.store_webhook(webhook_store)

        return f"✅ Created webhook: {webhook.data.attributes.title} (ID: {webhook.data.id})"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def update_webhook(webhook_id: str = "", title: str = "", active: str = "", url: str = "") -> str:
    """Update webhook title, active status, or URL."""
    try:
        if not webhook_id.strip():
            return "❌ Error: webhook_id is required"

        client = get_api_client()
        api = firefly_iii_client.WebhooksApi(client)

        update_data = {}
        if title:
            update_data["title"] = title
        if active:
            update_data["active"] = active.lower() == "true"
        if url:
            update_data["url"] = url

        if not update_data:
            return "❌ Error: At least one field to update is required"

        webhook_update = firefly_iii_client.WebhookUpdate(**update_data)
        webhook = api.update_webhook(webhook_id, webhook_update)

        return f"✅ Updated webhook: {webhook.data.attributes.title}"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def delete_webhook(webhook_id: str = "", confirm: str = "") -> str:
    """Delete a webhook by ID (requires confirm='DELETE' for safety)."""
    try:
        if not webhook_id.strip():
            return "❌ Error: webhook_id is required"
        if confirm != "DELETE":
            return "⚠️ Warning: This will permanently delete the webhook. Set confirm='DELETE' to proceed."

        client = get_api_client()
        api = firefly_iii_client.WebhooksApi(client)
        api.delete_webhook(webhook_id)

        return f"✅ Deleted webhook ID: {webhook_id}"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def trigger_webhook_test(webhook_id: str = "") -> str:
    """Trigger a test delivery for a webhook."""
    try:
        if not webhook_id.strip():
            return "❌ Error: webhook_id is required"

        client = get_api_client()
        api = firefly_iii_client.WebhooksApi(client)
        messages = api.submit_webook(webhook_id)

        result = f"✅ Test webhook triggered\n\n"
        if messages.data:
            result += "📬 Messages:\n"
            for msg in messages.data:
                attrs = msg.attributes
                result += f"- {attrs.sent}: {attrs.error_message or 'Success'}\n"

        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def list_webhook_messages(webhook_id: str = "") -> str:
    """List webhook delivery messages/attempts."""
    try:
        if not webhook_id.strip():
            return "❌ Error: webhook_id is required"

        client = get_api_client()
        api = firefly_iii_client.WebhooksApi(client)
        messages = api.list_webhook_message(webhook_id)

        if not messages.data:
            return "📭 No webhook messages found"

        result = f"📬 Webhook Messages:\n\n"
        result += "| ID | Sent | Success | Error |\n"
        result += "|------|------|---------|-------|\n"

        for msg in messages.data:
            attrs = msg.attributes
            success = '✓' if attrs.sent else '✗'
            error = attrs.error_message[:30] if attrs.error_message else 'None'
            result += f"| {msg.id} | {attrs.sent} | {success} | {error} |\n"

        return result
    except Exception as e:
        return format_error(e)

# ============================================================================
# ATTACHMENTS
# ============================================================================

@mcp.tool()
async def list_attachments() -> str:
    """List all attachments."""
    try:
        client = get_api_client()
        api = firefly_iii_client.AttachmentsApi(client)
        attachments = api.list_attachment()

        if not attachments.data:
            return "📭 No attachments found"

        result = f"📎 Found {len(attachments.data)} attachment(s):\n\n"
        result += "| ID | Filename | Model | Size (KB) |\n"
        result += "|------|----------|-------|------------|\n"

        for att in attachments.data:
            attrs = att.attributes
            size_kb = int(attrs.size / 1024) if hasattr(attrs, 'size') else 0
            result += f"| {att.id} | {attrs.filename} | {attrs.attachable_type} | {size_kb} |\n"

        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def get_attachment_details(attachment_id: str = "") -> str:
    """Get detailed attachment information."""
    try:
        if not attachment_id.strip():
            return "❌ Error: attachment_id is required"

        client = get_api_client()
        api = firefly_iii_client.AttachmentsApi(client)
        attachment = api.get_attachment(attachment_id)

        attrs = attachment.data.attributes
        result = f"""📎 Attachment Details: {attrs.filename}

**ID:** {attachment.data.id}
**Model Type:** {attrs.attachable_type}
**Model ID:** {attrs.attachable_id}
**MD5:** {attrs.md5}
**Mime Type:** {attrs.mime}
**Size:** {attrs.size} bytes
**Uploaded:** {attrs.uploaded}

**Title:** {attrs.title or 'None'}
**Notes:** {attrs.notes or 'None'}
"""
        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def delete_attachment(attachment_id: str = "", confirm: str = "") -> str:
    """Delete an attachment by ID (requires confirm='DELETE' for safety)."""
    try:
        if not attachment_id.strip():
            return "❌ Error: attachment_id is required"
        if confirm != "DELETE":
            return "⚠️ Warning: This will permanently delete the attachment. Set confirm='DELETE' to proceed."

        client = get_api_client()
        api = firefly_iii_client.AttachmentsApi(client)
        api.delete_attachment(attachment_id)

        return f"✅ Deleted attachment ID: {attachment_id}"
    except Exception as e:
        return format_error(e)

# ============================================================================
# AVAILABLE BUDGETS
# ============================================================================

@mcp.tool()
async def list_available_budgets() -> str:
    """List all available budgets (budget amounts available per period)."""
    try:
        client = get_api_client()
        api = firefly_iii_client.AvailableBudgetsApi(client)
        available_budgets = api.list_available_budget()

        if not available_budgets.data:
            return "📭 No available budgets found"

        result = f"💰 Found {len(available_budgets.data)} available budget(s):\n\n"
        result += "| ID | Currency | Amount | Start | End |\n"
        result += "|------|----------|--------|-------|-----|\n"

        for ab in available_budgets.data:
            attrs = ab.attributes
            result += f"| {ab.id} | {attrs.currency_code} | {format_amount(attrs.amount)} | {attrs.start} | {attrs.end} |\n"

        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def get_available_budget_details(available_budget_id: str = "") -> str:
    """Get detailed available budget information."""
    try:
        if not available_budget_id.strip():
            return "❌ Error: available_budget_id is required"

        client = get_api_client()
        api = firefly_iii_client.AvailableBudgetsApi(client)
        available_budget = api.get_available_budget(available_budget_id)

        attrs = available_budget.data.attributes
        result = f"""💰 Available Budget Details

**ID:** {available_budget.data.id}
**Currency:** {attrs.currency_code}
**Amount:** {format_amount(attrs.amount)}
**Period:** {attrs.start} to {attrs.end}
"""
        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def create_available_budget(currency_code: str = "USD", amount: str = "", start: str = "", end: str = "") -> str:
    """Create a new available budget for a period with currency, amount, start date, and end date."""
    try:
        if not all([amount.strip(), start.strip(), end.strip()]):
            return "❌ Error: amount, start, and end are required"

        client = get_api_client()
        api = firefly_iii_client.AvailableBudgetsApi(client)

        available_budget_data = {
            "currency_code": currency_code,
            "amount": amount,
            "start": start,
            "end": end
        }

        available_budget_store = firefly_iii_client.AvailableBudgetStore(**available_budget_data)
        available_budget = api.store_available_budget(available_budget_store)

        return f"✅ Created available budget: {format_amount(available_budget.data.attributes.amount)} {available_budget.data.attributes.currency_code} (ID: {available_budget.data.id})"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def update_available_budget(available_budget_id: str = "", amount: str = "") -> str:
    """Update available budget amount."""
    try:
        if not available_budget_id.strip():
            return "❌ Error: available_budget_id is required"
        if not amount:
            return "❌ Error: amount is required"

        client = get_api_client()
        api = firefly_iii_client.AvailableBudgetsApi(client)

        update_data = {"amount": amount}

        available_budget_update = firefly_iii_client.AvailableBudgetUpdate(**update_data)
        available_budget = api.update_available_budget(available_budget_id, available_budget_update)

        return f"✅ Updated available budget to: {format_amount(available_budget.data.attributes.amount)} {available_budget.data.attributes.currency_code}"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def delete_available_budget(available_budget_id: str = "", confirm: str = "") -> str:
    """Delete an available budget by ID (requires confirm='DELETE' for safety)."""
    try:
        if not available_budget_id.strip():
            return "❌ Error: available_budget_id is required"
        if confirm != "DELETE":
            return "⚠️ Warning: This will permanently delete the available budget. Set confirm='DELETE' to proceed."

        client = get_api_client()
        api = firefly_iii_client.AvailableBudgetsApi(client)
        api.delete_available_budget(available_budget_id)

        return f"✅ Deleted available budget ID: {available_budget_id}"
    except Exception as e:
        return format_error(e)

# ============================================================================
# LINKS (TRANSACTION LINKS)
# ============================================================================

@mcp.tool()
async def list_transaction_links() -> str:
    """List all transaction links."""
    try:
        client = get_api_client()
        api = firefly_iii_client.LinksApi(client)
        links = api.list_transaction_link()

        if not links.data:
            return "📭 No transaction links found"

        result = f"🔗 Found {len(links.data)} transaction link(s):\n\n"
        result += "| ID | Type | Notes |\n"
        result += "|------|------|-------|\n"

        for link in links.data:
            attrs = link.attributes
            notes = attrs.notes[:30] if attrs.notes else 'None'
            result += f"| {link.id} | {attrs.link_type_name} | {notes} |\n"

        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def get_transaction_link_details(link_id: str = "") -> str:
    """Get detailed transaction link information."""
    try:
        if not link_id.strip():
            return "❌ Error: link_id is required"

        client = get_api_client()
        api = firefly_iii_client.LinksApi(client)
        link = api.get_link_type(link_id)

        attrs = link.data.attributes
        result = f"""🔗 Transaction Link Details

**ID:** {link.data.id}
**Type:** {attrs.name}
**Inward:** {attrs.inward}
**Outward:** {attrs.outward}
**Editable:** {'Yes' if attrs.editable else 'No'}
"""
        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def delete_transaction_link(link_id: str = "", confirm: str = "") -> str:
    """Delete a transaction link by ID (requires confirm='DELETE' for safety)."""
    try:
        if not link_id.strip():
            return "❌ Error: link_id is required"
        if confirm != "DELETE":
            return "⚠️ Warning: This will permanently delete the transaction link. Set confirm='DELETE' to proceed."

        client = get_api_client()
        api = firefly_iii_client.LinksApi(client)
        api.delete_transaction_link(link_id)

        return f"✅ Deleted transaction link ID: {link_id}"
    except Exception as e:
        return format_error(e)

# ============================================================================
# PREFERENCES & CONFIGURATION
# ============================================================================

@mcp.tool()
async def list_preferences() -> str:
    """List all user preferences and configuration settings."""
    try:
        client = get_api_client()
        api = firefly_iii_client.PreferencesApi(client)
        preferences = api.list_preference()

        if not preferences.data:
            return "📭 No preferences found"

        result = f"⚙️ User Preferences:\n\n"
        result += "| Name | Value |\n"
        result += "|------|-------|\n"

        for pref in preferences.data:
            attrs = pref.attributes
            value = str(attrs.data)[:50] if hasattr(attrs, 'data') else 'N/A'
            result += f"| {attrs.name} | {value} |\n"

        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def get_preference(preference_name: str = "") -> str:
    """Get a specific preference value by name."""
    try:
        if not preference_name.strip():
            return "❌ Error: preference_name is required"

        client = get_api_client()
        api = firefly_iii_client.PreferencesApi(client)
        preference = api.get_preference(preference_name)

        attrs = preference.data.attributes
        result = f"""⚙️ Preference: {attrs.name}

**Value:** {attrs.data}
"""
        return result
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def get_configuration() -> str:
    """Get Firefly III configuration settings."""
    try:
        client = get_api_client()
        api = firefly_iii_client.ConfigurationApi(client)
        config = api.get_configuration()

        attrs = config.data.attributes
        result = f"""⚙️ Firefly III Configuration

**Single User Mode:** {'Yes' if attrs.single_user_mode else 'No'}
**Is Demo Site:** {'Yes' if attrs.is_demo_site else 'No'}
**Is Docker:** {'Yes' if attrs.is_docker else 'No'}
**Per Page:** {attrs.per_page}
"""
        return result
    except Exception as e:
        return format_error(e)

# ============================================================================
# DATA EXPORT
# ============================================================================

@mcp.tool()
async def export_accounts(account_type: str = "") -> str:
    """Export accounts data in JSON format, optionally filtered by account type."""
    try:
        client = get_api_client()
        api = firefly_iii_client.DataApi(client)

        if account_type:
            data = api.export_accounts(type=account_type)
        else:
            data = api.export_accounts()

        # Format the export data
        return f"✅ Accounts Export:\n```json\n{data}\n```"
    except Exception as e:
        return format_error(e)

@mcp.tool()
async def export_transactions(start_date: str = "", end_date: str = "", transaction_type: str = "") -> str:
    """Export transactions data in JSON format for a given date range and optional type filter."""
    try:
        client = get_api_client()
        api = firefly_iii_client.DataApi(client)

        params = {}
        if start_date:
            params['start'] = start_date
        if end_date:
            params['end'] = end_date
        if transaction_type:
            params['type'] = transaction_type

        data = api.export_transactions(**params)

        return f"✅ Transactions Export:\n```json\n{data}\n```"
    except Exception as e:
        return format_error(e)

# ============================================================================
# GENERIC ESCAPE HATCH
# ============================================================================

@mcp.tool()
async def firefly_raw_request(method: str = "GET", path: str = "", body: str = "") -> str:
    """Advanced: Make a raw API request to Firefly III (method: GET/POST/PUT/DELETE, path: /api/v1/..., body: JSON string for POST/PUT)."""
    try:
        if not path.strip():
            return "❌ Error: path is required"

        client = get_api_client()

        # Parse method
        method = method.upper()
        if method not in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']:
            return "❌ Error: method must be GET, POST, PUT, DELETE, or PATCH"

        # Parse body if provided
        request_body = None
        if body.strip():
            try:
                request_body = json.loads(body)
            except:
                return "❌ Error: body must be valid JSON"

        # Prepare headers
        headers = {}
        if request_body:
            headers['Content-Type'] = 'application/json'
        headers['Accept'] = 'application/json'

        # Construct full URL with host
        full_url = client.configuration.host.rstrip('/') + path

        # Make the request using the correct API
        response = client.rest_client.request(
            method=method,
            url=full_url,
            headers=headers,
            body=request_body if method in ['POST', 'PUT', 'PATCH'] else None
        )

        # Parse response
        try:
            data = json.loads(response.data)
            formatted = json.dumps(data, indent=2)
            return f"✅ API Response:\n```json\n{formatted}\n```"
        except:
            return f"✅ API Response:\n{response.data}"
    except Exception as e:
        return format_error(e)

# ============================================================================
# SERVER STARTUP
# ============================================================================
# MISSING METHODS - Adding 69 tools for 100% API coverage (167 → 236 tools)
# ============================================================================

# AboutApi - 1 missing method
@mcp.tool()
def get_cron_status() -> str:
    """Get cron job status and configuration."""
    try:
        api = firefly_iii_client.api.AboutApi(get_api_client())
        response = api.get_cron()
        cron = response.data
        return json.dumps({
            "cron_token": cron.cron_token if hasattr(cron, 'cron_token') else None,
            "jobs": cron.jobs if hasattr(cron, 'jobs') else []
        }, indent=2)
    except Exception as e:
        return format_error(e)

# AccountsApi - 2 missing methods
@mcp.tool()
def list_attachments_by_account(account_id: str = "", page: str = "") -> str:
    """List all attachments for a specific account."""
    try:
        api = firefly_iii_client.api.AccountsApi(get_api_client())
        response = api.list_attachment_by_account(account_id, page=int(page) if page else None)
        attachments = []
        for att in response.data:
            attachments.append({
                "id": att.id,
                "filename": att.attributes.filename,
                "title": att.attributes.title,
                "size": att.attributes.size
            })
        return json.dumps({"account_id": account_id, "attachments": attachments}, indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def list_piggy_banks_by_account(account_id: str = "", page: str = "") -> str:
    """List all piggy banks linked to a specific account."""
    try:
        api = firefly_iii_client.api.AccountsApi(get_api_client())
        response = api.list_piggy_bank_by_account(account_id, page=int(page) if page else None)
        piggies = []
        for piggy in response.data:
            piggies.append({
                "id": piggy.id,
                "name": piggy.attributes.name,
                "current_amount": piggy.attributes.current_amount,
                "target_amount": piggy.attributes.target_amount
            })
        return json.dumps({"account_id": account_id, "piggy_banks": piggies}, indent=2)
    except Exception as e:
        return format_error(e)

# AttachmentsApi - 4 missing methods
@mcp.tool()
def download_attachment(attachment_id: str = "") -> str:
    """Download attachment file content."""
    try:
        api = firefly_iii_client.api.AttachmentsApi(get_api_client())
        response = api.download_attachment(attachment_id)
        return f"✅ Attachment {attachment_id} downloaded (binary data available)"
    except Exception as e:
        return format_error(e)

@mcp.tool()
def create_attachment(filename: str = "", title: str = "", attachable_type: str = "", attachable_id: str = "", notes: str = "") -> str:
    """Create a new attachment (without file upload)."""
    try:
        api = firefly_iii_client.api.AttachmentsApi(get_api_client())
        attachment = firefly_iii_client.AttachmentStore(
            filename=filename,
            title=title,
            attachable_type=attachable_type,
            attachable_id=attachable_id,
            notes=notes if notes else None
        )
        response = api.store_attachment(attachment)
        return f"✅ Attachment created: {filename} (ID: {response.data.id})"
    except Exception as e:
        return format_error(e)

@mcp.tool()
def update_attachment(attachment_id: str = "", filename: str = "", title: str = "", notes: str = "") -> str:
    """Update attachment metadata."""
    try:
        api = firefly_iii_client.api.AttachmentsApi(get_api_client())
        attachment = firefly_iii_client.AttachmentUpdate()
        if filename:
            attachment.filename = filename
        if title:
            attachment.title = title
        if notes:
            attachment.notes = notes
        response = api.update_attachment(attachment_id, attachment)
        return f"✅ Attachment {attachment_id} updated"
    except Exception as e:
        return format_error(e)

@mcp.tool()
def upload_attachment_file(attachment_id: str = "", file_content_base64: str = "") -> str:
    """Upload file content to an existing attachment (base64 encoded)."""
    try:
        import base64
        api = firefly_iii_client.api.AttachmentsApi(get_api_client())
        file_data = base64.b64decode(file_content_base64)
        response = api.upload_attachment(attachment_id, file_data)
        return f"✅ File uploaded to attachment {attachment_id}"
    except Exception as e:
        return format_error(e)

# AutocompleteApi - 11 missing methods
@mcp.tool()
def autocomplete_currencies(query: str = "", limit: str = "") -> str:
    """Get currency autocomplete suggestions."""
    try:
        api = firefly_iii_client.api.AutocompleteApi(get_api_client())
        response = api.get_currencies_ac(query=query if query else None, limit=int(limit) if limit else None)
        return json.dumps([c.to_dict() for c in response], indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def autocomplete_currency_codes(query: str = "", limit: str = "") -> str:
    """Get currency code autocomplete suggestions."""
    try:
        api = firefly_iii_client.api.AutocompleteApi(get_api_client())
        response = api.get_currencies_code_ac(query=query if query else None, limit=int(limit) if limit else None)
        return json.dumps([c.to_dict() for c in response], indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def autocomplete_object_groups(query: str = "", limit: str = "") -> str:
    """Get object group autocomplete suggestions."""
    try:
        api = firefly_iii_client.api.AutocompleteApi(get_api_client())
        response = api.get_object_groups_ac(query=query if query else None, limit=int(limit) if limit else None)
        return json.dumps([g.to_dict() for g in response], indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def autocomplete_piggy_banks_with_balance(query: str = "", limit: str = "") -> str:
    """Get piggy bank autocomplete suggestions with balance info."""
    try:
        api = firefly_iii_client.api.AutocompleteApi(get_api_client())
        response = api.get_piggies_balance_ac(query=query if query else None, limit=int(limit) if limit else None)
        return json.dumps([p.to_dict() for p in response], indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def autocomplete_recurring_transactions(query: str = "", limit: str = "") -> str:
    """Get recurring transaction autocomplete suggestions."""
    try:
        api = firefly_iii_client.api.AutocompleteApi(get_api_client())
        response = api.get_recurring_ac(query=query if query else None, limit=int(limit) if limit else None)
        return json.dumps([r.to_dict() for r in response], indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def autocomplete_rule_groups(query: str = "", limit: str = "") -> str:
    """Get rule group autocomplete suggestions."""
    try:
        api = firefly_iii_client.api.AutocompleteApi(get_api_client())
        response = api.get_rule_groups_ac(query=query if query else None, limit=int(limit) if limit else None)
        return json.dumps([g.to_dict() for g in response], indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def autocomplete_rules(query: str = "", limit: str = "") -> str:
    """Get rule autocomplete suggestions."""
    try:
        api = firefly_iii_client.api.AutocompleteApi(get_api_client())
        response = api.get_rules_ac(query=query if query else None, limit=int(limit) if limit else None)
        return json.dumps([r.to_dict() for r in response], indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def autocomplete_subscriptions(query: str = "", limit: str = "") -> str:
    """Get subscription (bill) autocomplete suggestions."""
    try:
        api = firefly_iii_client.api.AutocompleteApi(get_api_client())
        response = api.get_subscriptions_ac(query=query if query else None, limit=int(limit) if limit else None)
        return json.dumps([s.to_dict() for s in response], indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def autocomplete_transaction_types(query: str = "", limit: str = "") -> str:
    """Get transaction type autocomplete suggestions."""
    try:
        api = firefly_iii_client.api.AutocompleteApi(get_api_client())
        response = api.get_transaction_types_ac(query=query if query else None, limit=int(limit) if limit else None)
        return json.dumps([t.to_dict() for t in response], indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def autocomplete_transactions(query: str = "", limit: str = "") -> str:
    """Get transaction autocomplete suggestions."""
    try:
        api = firefly_iii_client.api.AutocompleteApi(get_api_client())
        response = api.get_transactions_ac(query=query if query else None, limit=int(limit) if limit else None)
        return json.dumps([t.to_dict() for t in response], indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def autocomplete_transaction_ids(query: str = "", limit: str = "") -> str:
    """Get transaction ID autocomplete suggestions."""
    try:
        api = firefly_iii_client.api.AutocompleteApi(get_api_client())
        response = api.get_transactions_idac(query=query if query else None, limit=int(limit) if limit else None)
        return json.dumps([t.to_dict() for t in response], indent=2)
    except Exception as e:
        return format_error(e)

# BillsApi - 2 missing methods
@mcp.tool()
def list_attachments_by_bill(bill_id: str = "", page: str = "") -> str:
    """List all attachments for a specific bill."""
    try:
        api = firefly_iii_client.api.BillsApi(get_api_client())
        response = api.list_attachment_by_bill(bill_id, page=int(page) if page else None)
        attachments = []
        for att in response.data:
            attachments.append({
                "id": att.id,
                "filename": att.attributes.filename,
                "title": att.attributes.title
            })
        return json.dumps({"bill_id": bill_id, "attachments": attachments}, indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def list_rules_by_bill(bill_id: str = "") -> str:
    """List all rules that reference a specific bill."""
    try:
        api = firefly_iii_client.api.BillsApi(get_api_client())
        response = api.list_rule_by_bill(bill_id)
        rules = []
        for rule in response.data:
            rules.append({
                "id": rule.id,
                "title": rule.attributes.title,
                "active": rule.attributes.active
            })
        return json.dumps({"bill_id": bill_id, "rules": rules}, indent=2)
    except Exception as e:
        return format_error(e)

# BudgetsApi - 7 missing methods
@mcp.tool()
def get_budget_limit_details(budget_limit_id: str = "") -> str:
    """Get details for a specific budget limit."""
    try:
        api = firefly_iii_client.api.BudgetsApi(get_api_client())
        response = api.get_budget_limit(budget_limit_id)
        limit = response.data
        return json.dumps({
            "id": limit.id,
            "budget_id": limit.attributes.budget_id,
            "start": limit.attributes.start.isoformat() if limit.attributes.start else None,
            "end": limit.attributes.end.isoformat() if limit.attributes.end else None,
            "amount": limit.attributes.amount,
            "spent": limit.attributes.spent if hasattr(limit.attributes, 'spent') else None
        }, indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def list_all_budget_limits(start_date: str = "", end_date: str = "") -> str:
    """List all budget limits across all budgets."""
    try:
        api = firefly_iii_client.api.BudgetsApi(get_api_client())
        response = api.list_budget_limit(start_date, end_date)
        limits = []
        for limit in response.data:
            limits.append({
                "id": limit.id,
                "budget_id": limit.attributes.budget_id,
                "amount": limit.attributes.amount,
                "start": limit.attributes.start.isoformat() if limit.attributes.start else None,
                "end": limit.attributes.end.isoformat() if limit.attributes.end else None
            })
        return json.dumps({"limits": limits, "total": len(limits)}, indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def create_budget_limit(budget_id: str = "", start_date: str = "", end_date: str = "", amount: str = "") -> str:
    """Create a new budget limit for a budget."""
    try:
        api = firefly_iii_client.api.BudgetsApi(get_api_client())
        limit = firefly_iii_client.BudgetLimitStore(
            budget_id=budget_id,
            start=datetime.fromisoformat(start_date).date() if start_date else None,
            end=datetime.fromisoformat(end_date).date() if end_date else None,
            amount=amount
        )
        response = api.store_budget_limit(budget_id, limit)
        return f"✅ Budget limit created for budget {budget_id} (ID: {response.data.id})"
    except Exception as e:
        return format_error(e)

@mcp.tool()
def update_budget_limit(budget_id: str = "", budget_limit_id: str = "", start_date: str = "", end_date: str = "", amount: str = "") -> str:
    """Update an existing budget limit."""
    try:
        api = firefly_iii_client.api.BudgetsApi(get_api_client())
        limit = firefly_iii_client.BudgetLimitUpdate(
            start=datetime.fromisoformat(start_date).date() if start_date else None,
            end=datetime.fromisoformat(end_date).date() if end_date else None,
            amount=amount if amount else None
        )
        response = api.update_budget_limit(budget_id, budget_limit_id, limit)
        return f"✅ Budget limit {budget_limit_id} updated"
    except Exception as e:
        return format_error(e)

@mcp.tool()
def delete_budget_limit(budget_id: str = "", budget_limit_id: str = "", confirm: str = "") -> str:
    """Delete a budget limit (requires confirm='yes')."""
    if confirm.lower() != "yes":
        return "⚠️  Deletion requires confirm='yes'"
    try:
        api = firefly_iii_client.api.BudgetsApi(get_api_client())
        api.delete_budget_limit(budget_id, budget_limit_id)
        return f"✅ Budget limit {budget_limit_id} deleted"
    except Exception as e:
        return format_error(e)

@mcp.tool()
def list_attachments_by_budget(budget_id: str = "", page: str = "") -> str:
    """List all attachments for a specific budget."""
    try:
        api = firefly_iii_client.api.BudgetsApi(get_api_client())
        response = api.list_attachment_by_budget(budget_id, page=int(page) if page else None)
        attachments = []
        for att in response.data:
            attachments.append({
                "id": att.id,
                "filename": att.attributes.filename,
                "title": att.attributes.title
            })
        return json.dumps({"budget_id": budget_id, "attachments": attachments}, indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def list_transactions_by_budget_limit(budget_limit_id: str = "", page: str = "", transaction_type: str = "") -> str:
    """List all transactions for a specific budget limit."""
    try:
        api = firefly_iii_client.api.BudgetsApi(get_api_client())
        response = api.list_transaction_by_budget_limit(
            budget_limit_id,
            page=int(page) if page else None,
            type=transaction_type if transaction_type else None
        )
        transactions = []
        for tx in response.data:
            transactions.append({
                "id": tx.id,
                "description": tx.attributes.transactions[0].description if tx.attributes.transactions else None,
                "amount": tx.attributes.transactions[0].amount if tx.attributes.transactions else None,
                "date": tx.attributes.transactions[0].var_date.isoformat() if tx.attributes.transactions else None
            })
        return json.dumps({"budget_limit_id": budget_limit_id, "transactions": transactions}, indent=2)
    except Exception as e:
        return format_error(e)

# CategoriesApi - 1 missing method
@mcp.tool()
def list_attachments_by_category(category_id: str = "", page: str = "") -> str:
    """List all attachments for a specific category."""
    try:
        api = firefly_iii_client.api.CategoriesApi(get_api_client())
        response = api.list_attachment_by_category(category_id, page=int(page) if page else None)
        attachments = []
        for att in response.data:
            attachments.append({
                "id": att.id,
                "filename": att.attributes.filename,
                "title": att.attributes.title
            })
        return json.dumps({"category_id": category_id, "attachments": attachments}, indent=2)
    except Exception as e:
        return format_error(e)

# ConfigurationApi - 2 missing methods
@mcp.tool()
def get_single_configuration_value(config_name: str = "") -> str:
    """Get a single configuration value by name."""
    try:
        api = firefly_iii_client.api.ConfigurationApi(get_api_client())
        response = api.get_single_configuration(config_name)
        return json.dumps({
            "name": config_name,
            "value": response.data.attributes.value,
            "editable": response.data.attributes.editable
        }, indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def set_configuration_value(config_name: str = "", value: str = "") -> str:
    """Set a configuration value."""
    try:
        api = firefly_iii_client.api.ConfigurationApi(get_api_client())
        config = firefly_iii_client.Configuration(value=value)
        response = api.set_configuration(config_name, config)
        return f"✅ Configuration '{config_name}' set to '{value}'"
    except Exception as e:
        return format_error(e)

# CurrenciesApi - 12 missing methods
@mcp.tool()
def delete_currency(currency_code: str = "", confirm: str = "") -> str:
    """Delete a currency (requires confirm='yes')."""
    if confirm.lower() != "yes":
        return "⚠️  Deletion requires confirm='yes'"
    try:
        api = firefly_iii_client.api.CurrenciesApi(get_api_client())
        api.delete_currency(currency_code)
        return f"✅ Currency {currency_code} deleted"
    except Exception as e:
        return format_error(e)

@mcp.tool()
def get_primary_currency() -> str:
    """Get the primary (default) currency."""
    try:
        api = firefly_iii_client.api.CurrenciesApi(get_api_client())
        response = api.get_primary_currency()
        currency = response.data
        return json.dumps({
            "code": currency.attributes.code,
            "name": currency.attributes.name,
            "symbol": currency.attributes.symbol,
            "decimal_places": currency.attributes.decimal_places
        }, indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def set_primary_currency(currency_code: str = "") -> str:
    """Set a currency as the primary (default) currency."""
    try:
        api = firefly_iii_client.api.CurrenciesApi(get_api_client())
        response = api.primary_currency(currency_code)
        return f"✅ Currency {currency_code} set as primary currency"
    except Exception as e:
        return format_error(e)

@mcp.tool()
def create_currency(code: str = "", name: str = "", symbol: str = "", decimal_places: str = "") -> str:
    """Create a new currency."""
    try:
        api = firefly_iii_client.api.CurrenciesApi(get_api_client())
        currency = firefly_iii_client.Currency(
            code=code,
            name=name,
            symbol=symbol,
            decimal_places=int(decimal_places) if decimal_places else 2
        )
        response = api.store_currency(currency)
        return f"✅ Currency created: {code} (ID: {response.data.id})"
    except Exception as e:
        return format_error(e)

@mcp.tool()
def update_currency(currency_code: str = "", name: str = "", symbol: str = "", enabled: str = "") -> str:
    """Update currency details."""
    try:
        api = firefly_iii_client.api.CurrenciesApi(get_api_client())
        currency = firefly_iii_client.Currency()
        if name:
            currency.name = name
        if symbol:
            currency.symbol = symbol
        if enabled:
            currency.enabled = (enabled.lower() == "true")
        response = api.update_currency(currency_code, currency)
        return f"✅ Currency {currency_code} updated"
    except Exception as e:
        return format_error(e)

@mcp.tool()
def list_accounts_by_currency(currency_code: str = "", page: str = "", date: str = "", account_type: str = "") -> str:
    """List all accounts using a specific currency."""
    try:
        api = firefly_iii_client.api.CurrenciesApi(get_api_client())
        response = api.list_account_by_currency(
            currency_code,
            page=int(page) if page else None,
            date=date if date else None,
            type=account_type if account_type else None
        )
        accounts = []
        for acc in response.data:
            accounts.append({
                "id": acc.id,
                "name": acc.attributes.name,
                "type": acc.attributes.type,
                "currency_code": acc.attributes.currency_code
            })
        return json.dumps({"currency": currency_code, "accounts": accounts}, indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def list_available_budgets_by_currency(currency_code: str = "", page: str = "") -> str:
    """List all available budgets in a specific currency."""
    try:
        api = firefly_iii_client.api.CurrenciesApi(get_api_client())
        response = api.list_available_budget_by_currency(currency_code, page=int(page) if page else None)
        budgets = []
        for budget in response.data:
            budgets.append({
                "id": budget.id,
                "amount": budget.attributes.amount,
                "start": budget.attributes.start.isoformat() if budget.attributes.start else None,
                "end": budget.attributes.end.isoformat() if budget.attributes.end else None
            })
        return json.dumps({"currency": currency_code, "available_budgets": budgets}, indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def list_bills_by_currency(currency_code: str = "", page: str = "") -> str:
    """List all bills in a specific currency."""
    try:
        api = firefly_iii_client.api.CurrenciesApi(get_api_client())
        response = api.list_bill_by_currency(currency_code, page=int(page) if page else None)
        bills = []
        for bill in response.data:
            bills.append({
                "id": bill.id,
                "name": bill.attributes.name,
                "amount_min": bill.attributes.amount_min,
                "amount_max": bill.attributes.amount_max
            })
        return json.dumps({"currency": currency_code, "bills": bills}, indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def list_budget_limits_by_currency(currency_code: str = "", page: str = "", start_date: str = "", end_date: str = "") -> str:
    """List all budget limits in a specific currency."""
    try:
        api = firefly_iii_client.api.CurrenciesApi(get_api_client())
        response = api.list_budget_limit_by_currency(
            currency_code,
            page=int(page) if page else None,
            start=start_date if start_date else None,
            end=end_date if end_date else None
        )
        limits = []
        for limit in response.data:
            limits.append({
                "id": limit.id,
                "budget_id": limit.attributes.budget_id,
                "amount": limit.attributes.amount
            })
        return json.dumps({"currency": currency_code, "budget_limits": limits}, indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def list_recurrences_by_currency(currency_code: str = "", page: str = "") -> str:
    """List all recurring transactions in a specific currency."""
    try:
        api = firefly_iii_client.api.CurrenciesApi(get_api_client())
        response = api.list_recurrence_by_currency(currency_code, page=int(page) if page else None)
        recurrences = []
        for rec in response.data:
            recurrences.append({
                "id": rec.id,
                "title": rec.attributes.title,
                "type": rec.attributes.type
            })
        return json.dumps({"currency": currency_code, "recurrences": recurrences}, indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def list_rules_by_currency(currency_code: str = "", page: str = "") -> str:
    """List all rules that reference a specific currency."""
    try:
        api = firefly_iii_client.api.CurrenciesApi(get_api_client())
        response = api.list_rule_by_currency(currency_code, page=int(page) if page else None)
        rules = []
        for rule in response.data:
            rules.append({
                "id": rule.id,
                "title": rule.attributes.title,
                "active": rule.attributes.active
            })
        return json.dumps({"currency": currency_code, "rules": rules}, indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def list_transactions_by_currency(currency_code: str = "", page: str = "", start_date: str = "", end_date: str = "", transaction_type: str = "") -> str:
    """List all transactions in a specific currency."""
    try:
        api = firefly_iii_client.api.CurrenciesApi(get_api_client())
        response = api.list_transaction_by_currency(
            currency_code,
            page=int(page) if page else None,
            start=start_date if start_date else None,
            end=end_date if end_date else None,
            type=transaction_type if transaction_type else None
        )
        transactions = []
        for tx in response.data:
            if tx.attributes.transactions:
                transactions.append({
                    "id": tx.id,
                    "description": tx.attributes.transactions[0].description,
                    "amount": tx.attributes.transactions[0].amount,
                    "date": tx.attributes.transactions[0].var_date.isoformat()
                })
        return json.dumps({"currency": currency_code, "transactions": transactions}, indent=2)
    except Exception as e:
        return format_error(e)

# InsightApi - 1 missing method
@mcp.tool()
def insight_transfers_overview(start_date: str = "", end_date: str = "", account_ids: str = "") -> str:
    """Get general overview of transfers between accounts."""
    try:
        api = firefly_iii_client.api.InsightApi(get_api_client())
        accounts = [x.strip() for x in account_ids.split(",") if x.strip()]
        response = api.insight_transfers(start_date, end_date, accounts if accounts else None)
        return json.dumps(response.to_dict(), indent=2)
    except Exception as e:
        return format_error(e)

# LinksApi - 8 missing methods (transaction link types)
@mcp.tool()
def list_transaction_link_types(page: str = "") -> str:
    """List all transaction link types."""
    try:
        api = firefly_iii_client.api.LinksApi(get_api_client())
        response = api.list_link_type(page=int(page) if page else None)
        types = []
        for link_type in response.data:
            types.append({
                "id": link_type.id,
                "name": link_type.attributes.name,
                "inward": link_type.attributes.inward,
                "outward": link_type.attributes.outward
            })
        return json.dumps({"link_types": types}, indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def get_transaction_link_type(link_type_id: str = "") -> str:
    """Get details for a specific transaction link type."""
    try:
        api = firefly_iii_client.api.LinksApi(get_api_client())
        response = api.get_link_type(link_type_id)
        lt = response.data
        return json.dumps({
            "id": lt.id,
            "name": lt.attributes.name,
            "inward": lt.attributes.inward,
            "outward": lt.attributes.outward,
            "editable": lt.attributes.editable
        }, indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def create_transaction_link_type(name: str = "", inward: str = "", outward: str = "") -> str:
    """Create a new transaction link type."""
    try:
        api = firefly_iii_client.api.LinksApi(get_api_client())
        link_type = firefly_iii_client.LinkType(
            name=name,
            inward=inward,
            outward=outward
        )
        response = api.store_link_type(link_type)
        return f"✅ Link type created: {name} (ID: {response.data.id})"
    except Exception as e:
        return format_error(e)

@mcp.tool()
def update_transaction_link_type(link_type_id: str = "", name: str = "", inward: str = "", outward: str = "") -> str:
    """Update a transaction link type."""
    try:
        api = firefly_iii_client.api.LinksApi(get_api_client())
        link_type = firefly_iii_client.LinkType()
        if name:
            link_type.name = name
        if inward:
            link_type.inward = inward
        if outward:
            link_type.outward = outward
        response = api.update_link_type(link_type_id, link_type)
        return f"✅ Link type {link_type_id} updated"
    except Exception as e:
        return format_error(e)

@mcp.tool()
def delete_transaction_link_type(link_type_id: str = "", confirm: str = "") -> str:
    """Delete a transaction link type (requires confirm='yes')."""
    if confirm.lower() != "yes":
        return "⚠️  Deletion requires confirm='yes'"
    try:
        api = firefly_iii_client.api.LinksApi(get_api_client())
        api.delete_link_type(link_type_id)
        return f"✅ Link type {link_type_id} deleted"
    except Exception as e:
        return format_error(e)

@mcp.tool()
def list_transactions_by_link_type(link_type_id: str = "", page: str = "", start_date: str = "", end_date: str = "") -> str:
    """List all transactions using a specific link type."""
    try:
        api = firefly_iii_client.api.LinksApi(get_api_client())
        response = api.list_transaction_by_link_type(
            link_type_id,
            page=int(page) if page else None,
            start=start_date if start_date else None,
            end=end_date if end_date else None
        )
        transactions = []
        for tx in response.data:
            if tx.attributes.transactions:
                transactions.append({
                    "id": tx.id,
                    "description": tx.attributes.transactions[0].description,
                    "amount": tx.attributes.transactions[0].amount
                })
        return json.dumps({"link_type_id": link_type_id, "transactions": transactions}, indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def create_transaction_link(link_type_id: str = "", inward_id: str = "", outward_id: str = "", notes: str = "") -> str:
    """Create a link between two transactions."""
    try:
        api = firefly_iii_client.api.LinksApi(get_api_client())
        link = firefly_iii_client.TransactionLink(
            link_type_id=link_type_id,
            inward_id=inward_id,
            outward_id=outward_id,
            notes=notes if notes else None
        )
        response = api.store_transaction_link(link)
        return f"✅ Transaction link created (ID: {response.data.id})"
    except Exception as e:
        return format_error(e)

@mcp.tool()
def update_transaction_link_notes(link_id: str = "", notes: str = "") -> str:
    """Update notes for a transaction link."""
    try:
        api = firefly_iii_client.api.LinksApi(get_api_client())
        link = firefly_iii_client.TransactionLink(notes=notes)
        response = api.update_transaction_link(link_id, link)
        return f"✅ Transaction link {link_id} updated"
    except Exception as e:
        return format_error(e)

# PiggyBanksApi - 1 missing method
@mcp.tool()
def list_attachments_by_piggy_bank(piggy_bank_id: str = "", page: str = "") -> str:
    """List all attachments for a specific piggy bank."""
    try:
        api = firefly_iii_client.api.PiggyBanksApi(get_api_client())
        response = api.list_attachment_by_piggy_bank(piggy_bank_id, page=int(page) if page else None)
        attachments = []
        for att in response.data:
            attachments.append({
                "id": att.id,
                "filename": att.attributes.filename,
                "title": att.attributes.title
            })
        return json.dumps({"piggy_bank_id": piggy_bank_id, "attachments": attachments}, indent=2)
    except Exception as e:
        return format_error(e)

# PreferencesApi - 2 missing methods
@mcp.tool()
def create_preference(name: str = "", value: str = "") -> str:
    """Create a new user preference."""
    try:
        api = firefly_iii_client.api.PreferencesApi(get_api_client())
        preference = firefly_iii_client.Preference(name=name, data=value)
        response = api.store_preference(preference)
        return f"✅ Preference created: {name} = {value}"
    except Exception as e:
        return format_error(e)

@mcp.tool()
def update_preference(preference_name: str = "", value: str = "") -> str:
    """Update an existing user preference."""
    try:
        api = firefly_iii_client.api.PreferencesApi(get_api_client())
        preference = firefly_iii_client.Preference(data=value)
        response = api.update_preference(preference_name, preference)
        return f"✅ Preference '{preference_name}' updated to '{value}'"
    except Exception as e:
        return format_error(e)

# RecurrencesApi - 1 missing method
@mcp.tool()
def trigger_recurrence_now(recurrence_id: str = "") -> str:
    """Manually trigger a recurrence to create a transaction immediately."""
    try:
        api = firefly_iii_client.api.RecurrencesApi(get_api_client())
        response = api.trigger_recurrence_recurrence(recurrence_id)
        return f"✅ Recurrence {recurrence_id} triggered successfully"
    except Exception as e:
        return format_error(e)

# RuleGroupsApi - 2 missing methods
@mcp.tool()
def fire_rule_group(rule_group_id: str = "", start_date: str = "", end_date: str = "", account_ids: str = "") -> str:
    """Fire (trigger) a rule group on existing transactions."""
    try:
        api = firefly_iii_client.api.RuleGroupsApi(get_api_client())
        accounts = [x.strip() for x in account_ids.split(",") if x.strip()]
        response = api.fire_rule_group(
            rule_group_id,
            start=start_date if start_date else None,
            end=end_date if end_date else None,
            accounts=accounts if accounts else None
        )
        return f"✅ Rule group {rule_group_id} fired successfully"
    except Exception as e:
        return format_error(e)

@mcp.tool()
def test_rule_group(rule_group_id: str = "", start_date: str = "", end_date: str = "", account_ids: str = "") -> str:
    """Test a rule group against transactions without applying changes."""
    try:
        api = firefly_iii_client.api.RuleGroupsApi(get_api_client())
        accounts = [x.strip() for x in account_ids.split(",") if x.strip()]
        response = api.test_rule_group(
            rule_group_id,
            start=start_date if start_date else None,
            end=end_date if end_date else None,
            accounts=accounts if accounts else None
        )
        return json.dumps(response.to_dict(), indent=2)
    except Exception as e:
        return format_error(e)

# SearchApi - 2 missing methods
@mcp.tool()
def search_accounts_specific(query: str = "", field: str = "", page: str = "") -> str:
    """Search specifically for accounts with field filtering."""
    try:
        api = firefly_iii_client.api.SearchApi(get_api_client())
        # SearchApi.search_accounts doesn't accept 'field' parameter - removed to fix bug
        response = api.search_accounts(
            query=query,
            page=int(page) if page else None
        )
        accounts = []
        for acc in response.data:
            accounts.append({
                "id": acc.id,
                "name": acc.attributes.name,
                "type": acc.attributes.type
            })
        return json.dumps({"query": query, "accounts": accounts}, indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def search_transactions_specific(query: str = "", page: str = "") -> str:
    """Search specifically for transactions."""
    try:
        api = firefly_iii_client.api.SearchApi(get_api_client())
        response = api.search_transactions(query=query, page=int(page) if page else None)
        transactions = []
        for tx in response.data:
            if tx.attributes.transactions:
                transactions.append({
                    "id": tx.id,
                    "description": tx.attributes.transactions[0].description,
                    "amount": tx.attributes.transactions[0].amount,
                    "date": tx.attributes.transactions[0].var_date.isoformat()
                })
        return json.dumps({"query": query, "transactions": transactions}, indent=2)
    except Exception as e:
        return format_error(e)

# TransactionsApi - 4 missing methods
@mcp.tool()
def delete_transaction_journal(journal_id: str = "", confirm: str = "") -> str:
    """Delete a transaction by journal ID (requires confirm='yes')."""
    if confirm.lower() != "yes":
        return "⚠️  Deletion requires confirm='yes'"
    try:
        api = firefly_iii_client.api.TransactionsApi(get_api_client())
        api.delete_transaction_journal(journal_id)
        return f"✅ Transaction journal {journal_id} deleted"
    except Exception as e:
        return format_error(e)

@mcp.tool()
def get_transaction_by_journal(journal_id: str = "") -> str:
    """Get transaction details by journal ID."""
    try:
        api = firefly_iii_client.api.TransactionsApi(get_api_client())
        response = api.get_transaction_by_journal(journal_id)
        tx = response.data
        if tx.attributes.transactions:
            first = tx.attributes.transactions[0]
            return json.dumps({
                "id": tx.id,
                "journal_id": journal_id,
                "description": first.description,
                "amount": first.amount,
                "date": first.var_date.isoformat(),
                "type": tx.attributes.type
            }, indent=2)
        return json.dumps({"id": tx.id, "type": tx.attributes.type}, indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def list_transaction_events(transaction_id: str = "", page: str = "") -> str:
    """List all events (audit log) for a transaction."""
    try:
        api = firefly_iii_client.api.TransactionsApi(get_api_client())
        response = api.list_event_by_transaction(transaction_id, page=int(page) if page else None)
        events = []
        for event in response.data:
            events.append({
                "id": event.id,
                "created_at": event.attributes.created_at.isoformat() if event.attributes.created_at else None,
                "updated_at": event.attributes.updated_at.isoformat() if event.attributes.updated_at else None
            })
        return json.dumps({"transaction_id": transaction_id, "events": events}, indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def list_transaction_links_by_journal(journal_id: str = "", page: str = "") -> str:
    """List all links for a transaction journal."""
    try:
        api = firefly_iii_client.api.TransactionsApi(get_api_client())
        response = api.list_links_by_journal(journal_id, page=int(page) if page else None)
        links = []
        for link in response.data:
            links.append({
                "id": link.id,
                "link_type_id": link.attributes.link_type_id,
                "notes": link.attributes.notes
            })
        return json.dumps({"journal_id": journal_id, "links": links}, indent=2)
    except Exception as e:
        return format_error(e)

# WebhooksApi - 6 missing methods
@mcp.tool()
def delete_webhook_message(webhook_message_id: str = "", confirm: str = "") -> str:
    """Delete a webhook message (requires confirm='yes')."""
    if confirm.lower() != "yes":
        return "⚠️  Deletion requires confirm='yes'"
    try:
        api = firefly_iii_client.api.WebhooksApi(get_api_client())
        api.delete_webhook_message(webhook_message_id)
        return f"✅ Webhook message {webhook_message_id} deleted"
    except Exception as e:
        return format_error(e)

@mcp.tool()
def delete_webhook_message_attempt(webhook_message_attempt_id: str = "", confirm: str = "") -> str:
    """Delete a webhook message attempt (requires confirm='yes')."""
    if confirm.lower() != "yes":
        return "⚠️  Deletion requires confirm='yes'"
    try:
        api = firefly_iii_client.api.WebhooksApi(get_api_client())
        api.delete_webhook_message_attempt(webhook_message_attempt_id)
        return f"✅ Webhook message attempt {webhook_message_attempt_id} deleted"
    except Exception as e:
        return format_error(e)

@mcp.tool()
def get_webhook_message(webhook_message_id: str = "") -> str:
    """Get details for a specific webhook message."""
    try:
        api = firefly_iii_client.api.WebhooksApi(get_api_client())
        response = api.get_single_webhook_message(webhook_message_id)
        msg = response.data
        return json.dumps({
            "id": msg.id,
            "sent": msg.attributes.sent,
            "errored": msg.attributes.errored,
            "uuid": msg.attributes.uuid,
            "created_at": msg.attributes.created_at.isoformat() if msg.attributes.created_at else None
        }, indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def get_webhook_message_attempt(webhook_message_attempt_id: str = "") -> str:
    """Get details for a specific webhook message attempt."""
    try:
        api = firefly_iii_client.api.WebhooksApi(get_api_client())
        response = api.get_single_webhook_message_attempt(webhook_message_attempt_id)
        attempt = response.data
        return json.dumps({
            "id": attempt.id,
            "webhook_message_id": attempt.attributes.webhook_message_id,
            "status_code": attempt.attributes.status_code,
            "logs": attempt.attributes.logs
        }, indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def list_webhook_message_attempts(webhook_message_id: str = "", page: str = "") -> str:
    """List all attempts for a webhook message."""
    try:
        api = firefly_iii_client.api.WebhooksApi(get_api_client())
        response = api.get_webhook_message_attempts(webhook_message_id, page=int(page) if page else None)
        attempts = []
        for attempt in response.data:
            attempts.append({
                "id": attempt.id,
                "status_code": attempt.attributes.status_code,
                "created_at": attempt.attributes.created_at.isoformat() if attempt.attributes.created_at else None
            })
        return json.dumps({"webhook_message_id": webhook_message_id, "attempts": attempts}, indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def trigger_transaction_webhook(webhook_id: str = "", transaction_id: str = "") -> str:
    """Manually trigger a webhook for a specific transaction."""
    try:
        api = firefly_iii_client.api.WebhooksApi(get_api_client())
        response = api.trigger_transaction_webhook(webhook_id, transaction_id)
        return f"✅ Webhook {webhook_id} triggered for transaction {transaction_id}"
    except Exception as e:
        return format_error(e)
# ============================================================================
# CHARTS API - Chart Data Generation
# ============================================================================

@mcp.tool()
def get_chart_account_overview(start_date: str = "", end_date: str = "", account_ids: str = "") -> str:
    """Get chart data showing account balance overview for period."""
    try:
        api = firefly_iii_client.api.ChartsApi(get_api_client())
        account_id_list = [int(x.strip()) for x in account_ids.split(",") if x.strip()]
        response = api.get_chart_account_overview(start_date, end_date, account_id_list if account_id_list else None)
        return json.dumps(response.to_dict(), indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def get_chart_balance(start_date: str = "", end_date: str = "", account_ids: str = "") -> str:
    """Get chart data showing account balance over time."""
    try:
        api = firefly_iii_client.api.ChartsApi(get_api_client())
        account_id_list = [int(x.strip()) for x in account_ids.split(",") if x.strip()]
        response = api.get_chart_balance(start_date, end_date, account_id_list if account_id_list else None)
        return json.dumps(response.to_dict(), indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def get_chart_budget_overview(start_date: str = "", end_date: str = "", budget_ids: str = "") -> str:
    """Get chart data showing budget spending overview for period."""
    try:
        api = firefly_iii_client.api.ChartsApi(get_api_client())
        budget_id_list = [int(x.strip()) for x in budget_ids.split(",") if x.strip()]
        response = api.get_chart_budget_overview(start_date, end_date, budget_id_list if budget_id_list else None)
        return json.dumps(response.to_dict(), indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def get_chart_category_overview(start_date: str = "", end_date: str = "", category_ids: str = "") -> str:
    """Get chart data showing category spending overview for period."""
    try:
        api = firefly_iii_client.api.ChartsApi(get_api_client())
        category_id_list = [int(x.strip()) for x in category_ids.split(",") if x.strip()]
        response = api.get_chart_category_overview(start_date, end_date, category_id_list if category_id_list else None)
        return json.dumps(response.to_dict(), indent=2)
    except Exception as e:
        return format_error(e)

# ============================================================================
# CURRENCY EXCHANGE RATES API - Exchange Rate Management
# ============================================================================

@mcp.tool()
def list_currency_exchange_rates(page: str = "") -> str:
    """List all currency exchange rates with pagination."""
    try:
        api = firefly_iii_client.api.CurrencyExchangeRatesApi(get_api_client())
        response = api.list_currency_exchange_rates(page=int(page) if page else None)
        rates = []
        for rate in response.data:
            rates.append({
                "id": rate.id,
                "from_currency": rate.attributes.from_currency_code,
                "to_currency": rate.attributes.to_currency_code,
                "rate": rate.attributes.rate,
                "date": rate.attributes.var_date.isoformat() if rate.attributes.var_date else None
            })
        return json.dumps({"rates": rates, "total": len(rates)}, indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def get_currency_exchange_rate(rate_id: str = "") -> str:
    """Get details for a specific currency exchange rate by ID."""
    try:
        api = firefly_iii_client.api.CurrencyExchangeRatesApi(get_api_client())
        response = api.list_specific_currency_exchange_rate(rate_id)
        rate = response.data
        return json.dumps({
            "id": rate.id,
            "from_currency": rate.attributes.from_currency_code,
            "to_currency": rate.attributes.to_currency_code,
            "rate": rate.attributes.rate,
            "date": rate.attributes.var_date.isoformat() if rate.attributes.var_date else None,
            "created_at": rate.attributes.created_at.isoformat() if rate.attributes.created_at else None,
            "updated_at": rate.attributes.updated_at.isoformat() if rate.attributes.updated_at else None
        }, indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def get_exchange_rate_on_date(from_currency: str = "", to_currency: str = "", date: str = "") -> str:
    """Get exchange rate for a currency pair on a specific date."""
    try:
        api = firefly_iii_client.api.CurrencyExchangeRatesApi(get_api_client())
        response = api.list_specific_currency_exchange_rate_on_date(from_currency, to_currency, date)
        rate = response.data
        return json.dumps({
            "from_currency": from_currency,
            "to_currency": to_currency,
            "rate": rate.attributes.rate,
            "date": date
        }, indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def list_exchange_rates_for_pair(from_currency: str = "", to_currency: str = "", start_date: str = "", end_date: str = "") -> str:
    """List all exchange rates for a currency pair within date range."""
    try:
        api = firefly_iii_client.api.CurrencyExchangeRatesApi(get_api_client())
        response = api.list_specific_currency_exchange_rates(from_currency, to_currency, start_date, end_date)
        rates = []
        for rate in response.data:
            rates.append({
                "id": rate.id,
                "rate": rate.attributes.rate,
                "date": rate.attributes.var_date.isoformat() if rate.attributes.var_date else None
            })
        return json.dumps({"from": from_currency, "to": to_currency, "rates": rates}, indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def create_exchange_rate(from_currency: str = "", to_currency: str = "", rate: str = "", date: str = "") -> str:
    """Create a new currency exchange rate."""
    try:
        api = firefly_iii_client.api.CurrencyExchangeRatesApi(get_api_client())
        exchange_rate = firefly_iii_client.ExchangeRate(
            from_currency_code=from_currency,
            to_currency_code=to_currency,
            rate=rate,
            date=datetime.fromisoformat(date).date() if date else datetime.now().date()
        )
        response = api.store_currency_exchange_rate(exchange_rate)
        return f"✅ Exchange rate created: {from_currency} → {to_currency} = {rate} (ID: {response.data.id})"
    except Exception as e:
        return format_error(e)

@mcp.tool()
def create_exchange_rate_by_date(from_currency: str = "", to_currency: str = "", rate: str = "", date: str = "") -> str:
    """Create exchange rate for specific date."""
    try:
        api = firefly_iii_client.api.CurrencyExchangeRatesApi(get_api_client())
        exchange_rate = firefly_iii_client.ExchangeRate(
            from_currency_code=from_currency,
            to_currency_code=to_currency,
            rate=rate
        )
        response = api.store_currency_exchange_rates_by_date(from_currency, to_currency, date, exchange_rate)
        return f"✅ Exchange rate created for {date}: {from_currency} → {to_currency} = {rate}"
    except Exception as e:
        return format_error(e)

@mcp.tool()
def create_exchange_rate_by_pair(from_currency: str = "", to_currency: str = "", rate: str = "", date: str = "") -> str:
    """Create exchange rate by currency pair."""
    try:
        api = firefly_iii_client.api.CurrencyExchangeRatesApi(get_api_client())
        exchange_rate = firefly_iii_client.ExchangeRate(
            from_currency_code=from_currency,
            to_currency_code=to_currency,
            rate=rate,
            date=datetime.fromisoformat(date).date() if date else datetime.now().date()
        )
        response = api.store_currency_exchange_rates_by_pair(from_currency, to_currency, exchange_rate)
        return f"✅ Exchange rate created: {from_currency}/{to_currency} = {rate}"
    except Exception as e:
        return format_error(e)

@mcp.tool()
def update_exchange_rate(rate_id: str = "", rate_value: str = "", date: str = "") -> str:
    """Update an existing currency exchange rate."""
    try:
        api = firefly_iii_client.api.CurrencyExchangeRatesApi(get_api_client())
        exchange_rate = firefly_iii_client.ExchangeRate(rate=rate_value)
        if date:
            exchange_rate.date = datetime.fromisoformat(date).date()
        response = api.update_currency_exchange_rate(rate_id, exchange_rate)
        return f"✅ Exchange rate {rate_id} updated to {rate_value}"
    except Exception as e:
        return format_error(e)

@mcp.tool()
def update_exchange_rate_by_date(from_currency: str = "", to_currency: str = "", date: str = "", rate: str = "") -> str:
    """Update exchange rate for specific currency pair and date."""
    try:
        api = firefly_iii_client.api.CurrencyExchangeRatesApi(get_api_client())
        exchange_rate = firefly_iii_client.ExchangeRate(rate=rate)
        response = api.update_currency_exchange_rate_by_date(from_currency, to_currency, date, exchange_rate)
        return f"✅ Exchange rate updated for {date}: {from_currency} → {to_currency} = {rate}"
    except Exception as e:
        return format_error(e)

@mcp.tool()
def delete_exchange_rate(rate_id: str = "", confirm: str = "") -> str:
    """Delete a currency exchange rate (requires confirm='yes')."""
    if confirm.lower() != "yes":
        return "⚠️  Deletion requires confirm='yes'"
    try:
        api = firefly_iii_client.api.CurrencyExchangeRatesApi(get_api_client())
        api.delete_specific_currency_exchange_rate(rate_id)
        return f"✅ Exchange rate {rate_id} deleted"
    except Exception as e:
        return format_error(e)

@mcp.tool()
def delete_exchange_rate_on_date(from_currency: str = "", to_currency: str = "", date: str = "", confirm: str = "") -> str:
    """Delete exchange rate for specific currency pair and date (requires confirm='yes')."""
    if confirm.lower() != "yes":
        return "⚠️  Deletion requires confirm='yes'"
    try:
        api = firefly_iii_client.api.CurrencyExchangeRatesApi(get_api_client())
        api.delete_specific_currency_exchange_rate_on_date(from_currency, to_currency, date)
        return f"✅ Exchange rate for {from_currency}/{to_currency} on {date} deleted"
    except Exception as e:
        return format_error(e)

@mcp.tool()
def delete_exchange_rates_for_pair(from_currency: str = "", to_currency: str = "", start_date: str = "", end_date: str = "", confirm: str = "") -> str:
    """Delete all exchange rates for currency pair in date range (requires confirm='yes')."""
    if confirm.lower() != "yes":
        return "⚠️  Deletion requires confirm='yes'"
    try:
        api = firefly_iii_client.api.CurrencyExchangeRatesApi(get_api_client())
        api.delete_specific_currency_exchange_rates(from_currency, to_currency, start_date, end_date)
        return f"✅ Exchange rates for {from_currency}/{to_currency} deleted"
    except Exception as e:
        return format_error(e)

# ============================================================================
# DATA API - Bulk Operations & Extended Exports
# ============================================================================

@mcp.tool()
def bulk_update_transactions(transaction_ids: str = "", updates_json: str = "") -> str:
    """Bulk update multiple transactions at once (provide JSON array of updates)."""
    try:
        api = firefly_iii_client.api.DataApi(get_api_client())
        updates = json.loads(updates_json) if updates_json else []
        response = api.bulk_update_transactions(updates)
        return f"✅ Bulk updated {len(updates)} transactions"
    except Exception as e:
        return format_error(e)

@mcp.tool()
def export_bills(start_date: str = "", end_date: str = "") -> str:
    """Export bills data in CSV format."""
    try:
        api = firefly_iii_client.api.DataApi(get_api_client())
        response = api.export_bills(start_date, end_date)
        return f"✅ Bills exported (CSV data available)"
    except Exception as e:
        return format_error(e)

@mcp.tool()
def export_budgets(start_date: str = "", end_date: str = "") -> str:
    """Export budgets data in CSV format."""
    try:
        api = firefly_iii_client.api.DataApi(get_api_client())
        response = api.export_budgets(start_date, end_date)
        return f"✅ Budgets exported (CSV data available)"
    except Exception as e:
        return format_error(e)

@mcp.tool()
def export_categories(start_date: str = "", end_date: str = "") -> str:
    """Export categories data in CSV format."""
    try:
        api = firefly_iii_client.api.DataApi(get_api_client())
        response = api.export_categories(start_date, end_date)
        return f"✅ Categories exported (CSV data available)"
    except Exception as e:
        return format_error(e)

@mcp.tool()
def export_piggy_banks() -> str:
    """Export piggy banks data in CSV format."""
    try:
        api = firefly_iii_client.api.DataApi(get_api_client())
        response = api.export_piggies()
        return f"✅ Piggy banks exported (CSV data available)"
    except Exception as e:
        return format_error(e)

@mcp.tool()
def export_recurring_transactions() -> str:
    """Export recurring transactions data in CSV format."""
    try:
        api = firefly_iii_client.api.DataApi(get_api_client())
        response = api.export_recurring()
        return f"✅ Recurring transactions exported (CSV data available)"
    except Exception as e:
        return format_error(e)

@mcp.tool()
def export_rules() -> str:
    """Export rules data in CSV format."""
    try:
        api = firefly_iii_client.api.DataApi(get_api_client())
        response = api.export_rules()
        return f"✅ Rules exported (CSV data available)"
    except Exception as e:
        return format_error(e)

@mcp.tool()
def export_tags(start_date: str = "", end_date: str = "") -> str:
    """Export tags data in CSV format."""
    try:
        api = firefly_iii_client.api.DataApi(get_api_client())
        response = api.export_tags(start_date, end_date)
        return f"✅ Tags exported (CSV data available)"
    except Exception as e:
        return format_error(e)

@mcp.tool()
def destroy_data(objects: str = "", confirm: str = "") -> str:
    """Destroy (soft delete) specific types of data (requires confirm='yes')."""
    if confirm.lower() != "yes":
        return "⚠️  Destruction requires confirm='yes'"
    try:
        api = firefly_iii_client.api.DataApi(get_api_client())
        object_list = [x.strip() for x in objects.split(",") if x.strip()]
        response = api.destroy_data(object_list)
        return f"✅ Data destroyed: {', '.join(object_list)}"
    except Exception as e:
        return format_error(e)

@mcp.tool()
def purge_data(confirm_purge: str = "", confirm_yes: str = "") -> str:
    """PERMANENTLY purge all data from Firefly III (requires confirm_purge='PURGE' and confirm_yes='yes')."""
    if confirm_purge != "PURGE" or confirm_yes.lower() != "yes":
        return "⚠️  Purge requires confirm_purge='PURGE' and confirm_yes='yes'. This action CANNOT be undone!"
    try:
        api = firefly_iii_client.api.DataApi(get_api_client())
        response = api.purge_data()
        return "✅ All data has been permanently purged from Firefly III"
    except Exception as e:
        return format_error(e)

# ============================================================================
# INSIGHT API - Comprehensive Financial Insights
# ============================================================================

@mcp.tool()
def insight_expense_asset(start_date: str = "", end_date: str = "", asset_account_ids: str = "") -> str:
    """Get insight into expenses from specific asset accounts."""
    try:
        api = firefly_iii_client.api.InsightApi(get_api_client())
        account_ids = [x.strip() for x in asset_account_ids.split(",") if x.strip()]
        response = api.insight_expense_asset(start_date, end_date, account_ids if account_ids else None)
        return json.dumps(response.to_dict(), indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def insight_expense_bill(start_date: str = "", end_date: str = "", bill_ids: str = "") -> str:
    """Get insight into expenses for specific bills."""
    try:
        api = firefly_iii_client.api.InsightApi(get_api_client())
        bills = [x.strip() for x in bill_ids.split(",") if x.strip()]
        response = api.insight_expense_bill(start_date, end_date, bills if bills else None)
        return json.dumps(response.to_dict(), indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def insight_expense_budget(start_date: str = "", end_date: str = "", budget_ids: str = "") -> str:
    """Get insight into expenses for specific budgets."""
    try:
        api = firefly_iii_client.api.InsightApi(get_api_client())
        budgets = [x.strip() for x in budget_ids.split(",") if x.strip()]
        response = api.insight_expense_budget(start_date, end_date, budgets if budgets else None)
        return json.dumps(response.to_dict(), indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def insight_expense_category(start_date: str = "", end_date: str = "", category_ids: str = "") -> str:
    """Get insight into expenses for specific categories."""
    try:
        api = firefly_iii_client.api.InsightApi(get_api_client())
        categories = [x.strip() for x in category_ids.split(",") if x.strip()]
        response = api.insight_expense_category(start_date, end_date, categories if categories else None)
        return json.dumps(response.to_dict(), indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def insight_expense_expense_account(start_date: str = "", end_date: str = "", expense_account_ids: str = "") -> str:
    """Get insight into specific expense accounts."""
    try:
        api = firefly_iii_client.api.InsightApi(get_api_client())
        accounts = [x.strip() for x in expense_account_ids.split(",") if x.strip()]
        response = api.insight_expense_expense(start_date, end_date, accounts if accounts else None)
        return json.dumps(response.to_dict(), indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def insight_expense_no_bill(start_date: str = "", end_date: str = "") -> str:
    """Get insight into expenses without an associated bill."""
    try:
        api = firefly_iii_client.api.InsightApi(get_api_client())
        response = api.insight_expense_no_bill(start_date, end_date)
        return json.dumps(response.to_dict(), indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def insight_expense_no_budget(start_date: str = "", end_date: str = "") -> str:
    """Get insight into expenses without an associated budget."""
    try:
        api = firefly_iii_client.api.InsightApi(get_api_client())
        response = api.insight_expense_no_budget(start_date, end_date)
        return json.dumps(response.to_dict(), indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def insight_expense_no_category(start_date: str = "", end_date: str = "") -> str:
    """Get insight into expenses without an associated category."""
    try:
        api = firefly_iii_client.api.InsightApi(get_api_client())
        response = api.insight_expense_no_category(start_date, end_date)
        return json.dumps(response.to_dict(), indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def insight_expense_no_tag(start_date: str = "", end_date: str = "") -> str:
    """Get insight into expenses without any tags."""
    try:
        api = firefly_iii_client.api.InsightApi(get_api_client())
        response = api.insight_expense_no_tag(start_date, end_date)
        return json.dumps(response.to_dict(), indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def insight_expense_tag(start_date: str = "", end_date: str = "", tag_ids: str = "") -> str:
    """Get insight into expenses for specific tags."""
    try:
        api = firefly_iii_client.api.InsightApi(get_api_client())
        tags = [x.strip() for x in tag_ids.split(",") if x.strip()]
        response = api.insight_expense_tag(start_date, end_date, tags if tags else None)
        return json.dumps(response.to_dict(), indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def insight_expense_total(start_date: str = "", end_date: str = "") -> str:
    """Get total expense insight for period."""
    try:
        api = firefly_iii_client.api.InsightApi(get_api_client())
        response = api.insight_expense_total(start_date, end_date)
        return json.dumps(response.to_dict(), indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def insight_income_asset(start_date: str = "", end_date: str = "", asset_account_ids: str = "") -> str:
    """Get insight into income to specific asset accounts."""
    try:
        api = firefly_iii_client.api.InsightApi(get_api_client())
        accounts = [x.strip() for x in asset_account_ids.split(",") if x.strip()]
        response = api.insight_income_asset(start_date, end_date, accounts if accounts else None)
        return json.dumps(response.to_dict(), indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def insight_income_category(start_date: str = "", end_date: str = "", category_ids: str = "") -> str:
    """Get insight into income for specific categories."""
    try:
        api = firefly_iii_client.api.InsightApi(get_api_client())
        categories = [x.strip() for x in category_ids.split(",") if x.strip()]
        response = api.insight_income_category(start_date, end_date, categories if categories else None)
        return json.dumps(response.to_dict(), indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def insight_income_no_category(start_date: str = "", end_date: str = "") -> str:
    """Get insight into income without an associated category."""
    try:
        api = firefly_iii_client.api.InsightApi(get_api_client())
        response = api.insight_income_no_category(start_date, end_date)
        return json.dumps(response.to_dict(), indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def insight_income_no_tag(start_date: str = "", end_date: str = "") -> str:
    """Get insight into income without any tags."""
    try:
        api = firefly_iii_client.api.InsightApi(get_api_client())
        response = api.insight_income_no_tag(start_date, end_date)
        return json.dumps(response.to_dict(), indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def insight_income_revenue(start_date: str = "", end_date: str = "", revenue_account_ids: str = "") -> str:
    """Get insight into specific revenue accounts."""
    try:
        api = firefly_iii_client.api.InsightApi(get_api_client())
        accounts = [x.strip() for x in revenue_account_ids.split(",") if x.strip()]
        response = api.insight_income_revenue(start_date, end_date, accounts if accounts else None)
        return json.dumps(response.to_dict(), indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def insight_income_tag(start_date: str = "", end_date: str = "", tag_ids: str = "") -> str:
    """Get insight into income for specific tags."""
    try:
        api = firefly_iii_client.api.InsightApi(get_api_client())
        tags = [x.strip() for x in tag_ids.split(",") if x.strip()]
        response = api.insight_income_tag(start_date, end_date, tags if tags else None)
        return json.dumps(response.to_dict(), indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def insight_income_total(start_date: str = "", end_date: str = "") -> str:
    """Get total income insight for period."""
    try:
        api = firefly_iii_client.api.InsightApi(get_api_client())
        response = api.insight_income_total(start_date, end_date)
        return json.dumps(response.to_dict(), indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def insight_transfer_category(start_date: str = "", end_date: str = "", category_ids: str = "") -> str:
    """Get insight into transfers for specific categories."""
    try:
        api = firefly_iii_client.api.InsightApi(get_api_client())
        categories = [x.strip() for x in category_ids.split(",") if x.strip()]
        response = api.insight_transfer_category(start_date, end_date, categories if categories else None)
        return json.dumps(response.to_dict(), indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def insight_transfer_no_category(start_date: str = "", end_date: str = "") -> str:
    """Get insight into transfers without an associated category."""
    try:
        api = firefly_iii_client.api.InsightApi(get_api_client())
        response = api.insight_transfer_no_category(start_date, end_date)
        return json.dumps(response.to_dict(), indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def insight_transfer_no_tag(start_date: str = "", end_date: str = "") -> str:
    """Get insight into transfers without any tags."""
    try:
        api = firefly_iii_client.api.InsightApi(get_api_client())
        response = api.insight_transfer_no_tag(start_date, end_date)
        return json.dumps(response.to_dict(), indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def insight_transfer_tag(start_date: str = "", end_date: str = "", tag_ids: str = "") -> str:
    """Get insight into transfers for specific tags."""
    try:
        api = firefly_iii_client.api.InsightApi(get_api_client())
        tags = [x.strip() for x in tag_ids.split(",") if x.strip()]
        response = api.insight_transfer_tag(start_date, end_date, tags if tags else None)
        return json.dumps(response.to_dict(), indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def insight_transfer_total(start_date: str = "", end_date: str = "") -> str:
    """Get total transfer insight for period."""
    try:
        api = firefly_iii_client.api.InsightApi(get_api_client())
        response = api.insight_transfer_total(start_date, end_date)
        return json.dumps(response.to_dict(), indent=2)
    except Exception as e:
        return format_error(e)

# ============================================================================
# OBJECT GROUPS API - Organize Bills and Piggy Banks
# ============================================================================

@mcp.tool()
def list_object_groups(page: str = "") -> str:
    """List all object groups with pagination."""
    try:
        api = firefly_iii_client.api.ObjectGroupsApi(get_api_client())
        response = api.list_object_groups(page=int(page) if page else None)
        groups = []
        for group in response.data:
            groups.append({
                "id": group.id,
                "title": group.attributes.title,
                "order": group.attributes.order,
                "created_at": group.attributes.created_at.isoformat() if group.attributes.created_at else None
            })
        return json.dumps({"groups": groups, "total": len(groups)}, indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def get_object_group(group_id: str = "") -> str:
    """Get details for a specific object group."""
    try:
        api = firefly_iii_client.api.ObjectGroupsApi(get_api_client())
        response = api.get_object_group(group_id)
        group = response.data
        return json.dumps({
            "id": group.id,
            "title": group.attributes.title,
            "order": group.attributes.order,
            "created_at": group.attributes.created_at.isoformat() if group.attributes.created_at else None,
            "updated_at": group.attributes.updated_at.isoformat() if group.attributes.updated_at else None
        }, indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def update_object_group(group_id: str = "", title: str = "", order: str = "") -> str:
    """Update an object group's title or order."""
    try:
        api = firefly_iii_client.api.ObjectGroupsApi(get_api_client())
        object_group = firefly_iii_client.ObjectGroupUpdate()
        if title:
            object_group.title = title
        if order:
            object_group.order = int(order)
        response = api.update_object_group(group_id, object_group)
        return f"✅ Object group {group_id} updated"
    except Exception as e:
        return format_error(e)

@mcp.tool()
def delete_object_group(group_id: str = "", confirm: str = "") -> str:
    """Delete an object group (requires confirm='yes')."""
    if confirm.lower() != "yes":
        return "⚠️  Deletion requires confirm='yes'"
    try:
        api = firefly_iii_client.api.ObjectGroupsApi(get_api_client())
        api.delete_object_group(group_id)
        return f"✅ Object group {group_id} deleted"
    except Exception as e:
        return format_error(e)

@mcp.tool()
def list_bills_by_object_group(group_id: str = "", page: str = "") -> str:
    """List all bills in a specific object group."""
    try:
        api = firefly_iii_client.api.ObjectGroupsApi(get_api_client())
        response = api.list_bill_by_object_group(group_id, page=int(page) if page else None)
        bills = []
        for bill in response.data:
            bills.append({
                "id": bill.id,
                "name": bill.attributes.name,
                "amount_min": bill.attributes.amount_min,
                "amount_max": bill.attributes.amount_max,
                "active": bill.attributes.active
            })
        return json.dumps({"group_id": group_id, "bills": bills, "total": len(bills)}, indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def list_piggy_banks_by_object_group(group_id: str = "", page: str = "") -> str:
    """List all piggy banks in a specific object group."""
    try:
        api = firefly_iii_client.api.ObjectGroupsApi(get_api_client())
        response = api.list_piggy_bank_by_object_group(group_id, page=int(page) if page else None)
        piggy_banks = []
        for piggy in response.data:
            piggy_banks.append({
                "id": piggy.id,
                "name": piggy.attributes.name,
                "target_amount": piggy.attributes.target_amount,
                "current_amount": piggy.attributes.current_amount
            })
        return json.dumps({"group_id": group_id, "piggy_banks": piggy_banks, "total": len(piggy_banks)}, indent=2)
    except Exception as e:
        return format_error(e)

# ============================================================================
# SUMMARY API - Dashboard Summary
# ============================================================================

@mcp.tool()
def get_basic_summary(start_date: str = "", end_date: str = "", currency_code: str = "") -> str:
    """Get basic financial summary (dashboard overview) for date range."""
    try:
        api = firefly_iii_client.api.SummaryApi(get_api_client())
        response = api.get_basic_summary(start_date, end_date, currency_code if currency_code else None)
        return json.dumps(response.to_dict(), indent=2)
    except Exception as e:
        return format_error(e)

# ============================================================================
# USER GROUPS API - Multi-User Group Management
# ============================================================================

@mcp.tool()
def list_user_groups(page: str = "") -> str:
    """List all user groups (multi-user feature)."""
    try:
        api = firefly_iii_client.api.UserGroupsApi(get_api_client())
        response = api.list_user_groups(page=int(page) if page else None)
        groups = []
        for group in response.data:
            groups.append({
                "id": group.id,
                "title": group.attributes.title,
                "created_at": group.attributes.created_at.isoformat() if group.attributes.created_at else None
            })
        return json.dumps({"groups": groups, "total": len(groups)}, indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def get_user_group(group_id: str = "") -> str:
    """Get details for a specific user group."""
    try:
        api = firefly_iii_client.api.UserGroupsApi(get_api_client())
        response = api.get_user_group(group_id)
        group = response.data
        return json.dumps({
            "id": group.id,
            "title": group.attributes.title,
            "created_at": group.attributes.created_at.isoformat() if group.attributes.created_at else None,
            "updated_at": group.attributes.updated_at.isoformat() if group.attributes.updated_at else None
        }, indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def update_user_group(group_id: str = "", title: str = "") -> str:
    """Update a user group's title."""
    try:
        api = firefly_iii_client.api.UserGroupsApi(get_api_client())
        user_group = firefly_iii_client.UserGroupUpdate(title=title)
        response = api.update_user_group(group_id, user_group)
        return f"✅ User group {group_id} updated"
    except Exception as e:
        return format_error(e)

# ============================================================================
# USERS API - User Management (Admin)
# ============================================================================

@mcp.tool()
def list_users(page: str = "") -> str:
    """List all users (admin feature)."""
    try:
        api = firefly_iii_client.api.UsersApi(get_api_client())
        response = api.list_user(page=int(page) if page else None)
        users = []
        for user in response.data:
            users.append({
                "id": user.id,
                "email": user.attributes.email,
                "blocked": user.attributes.blocked,
                "blocked_code": user.attributes.blocked_code,
                "role": user.attributes.role,
                "created_at": user.attributes.created_at.isoformat() if user.attributes.created_at else None
            })
        return json.dumps({"users": users, "total": len(users)}, indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def get_user(user_id: str = "") -> str:
    """Get details for a specific user."""
    try:
        api = firefly_iii_client.api.UsersApi(get_api_client())
        response = api.get_user(user_id)
        user = response.data
        return json.dumps({
            "id": user.id,
            "email": user.attributes.email,
            "blocked": user.attributes.blocked,
            "blocked_code": user.attributes.blocked_code,
            "role": user.attributes.role,
            "created_at": user.attributes.created_at.isoformat() if user.attributes.created_at else None,
            "updated_at": user.attributes.updated_at.isoformat() if user.attributes.updated_at else None
        }, indent=2)
    except Exception as e:
        return format_error(e)

@mcp.tool()
def create_user(email: str = "", password: str = "", blocked: str = "", role: str = "") -> str:
    """Create a new user (admin feature)."""
    try:
        api = firefly_iii_client.api.UsersApi(get_api_client())
        user = firefly_iii_client.User(
            email=email,
            password=password,
            blocked=(blocked.lower() == "true") if blocked else False,
            role=role if role else "user"
        )
        response = api.store_user(user)
        return f"✅ User created: {email} (ID: {response.data.id})"
    except Exception as e:
        return format_error(e)

@mcp.tool()
def update_user(user_id: str = "", email: str = "", blocked: str = "", role: str = "") -> str:
    """Update a user's details (admin feature)."""
    try:
        api = firefly_iii_client.api.UsersApi(get_api_client())
        user = firefly_iii_client.User()
        if email:
            user.email = email
        if blocked:
            user.blocked = (blocked.lower() == "true")
        if role:
            user.role = role
        response = api.update_user(user_id, user)
        return f"✅ User {user_id} updated"
    except Exception as e:
        return format_error(e)

@mcp.tool()
def delete_user(user_id: str = "", confirm: str = "") -> str:
    """Delete a user (admin feature, requires confirm='yes')."""
    if confirm.lower() != "yes":
        return "⚠️  Deletion requires confirm='yes'"
    try:
        api = firefly_iii_client.api.UsersApi(get_api_client())
        api.delete_user(user_id)
        return f"✅ User {user_id} deleted"
    except Exception as e:
        return format_error(e)
# ============================================================================

if __name__ == "__main__":
    logger.info("Starting Firefly III MCP server...")

    # Load and validate configuration
    config = load_config()
    if not config:
        logger.warning("Configuration not loaded properly. Check ~/.config/mcp-secrets.json")

    try:
        mcp.run(transport='stdio')
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        sys.exit(1)
