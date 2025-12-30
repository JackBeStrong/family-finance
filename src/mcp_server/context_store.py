"""
Financial Context Store

Manages the financial context store (YAML file) for AI-powered reporting.
Provides methods to load and query the context for:
- Account information and mappings
- Property portfolio details
- Entity recognition (employers, merchants, etc.)
- Category rules
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

# Context store path - can be overridden by environment variable
DEFAULT_CONTEXT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config",
    "financial-context.yaml"
)


class FinancialContextStore:
    """
    Manages the financial context store (YAML file).
    
    Provides methods to load and query the context for:
    - Account information and mappings
    - Property portfolio details
    - Entity recognition (employers, merchants, etc.)
    - Category rules
    """
    
    def __init__(self, context_path: Optional[str] = None):
        self.context_path = context_path or os.environ.get(
            "FINANCIAL_CONTEXT_PATH",
            DEFAULT_CONTEXT_PATH
        )
        self._context: Optional[Dict] = None
        self._load_time: Optional[datetime] = None
    
    def _load_context(self) -> Dict:
        """Load context from YAML file, with caching."""
        # Check if file exists
        if not os.path.exists(self.context_path):
            logger.warning(f"Context file not found: {self.context_path}")
            return {"error": f"Context file not found: {self.context_path}"}
        
        # Check if we need to reload (file modified)
        file_mtime = datetime.fromtimestamp(os.path.getmtime(self.context_path))
        if self._context is not None and self._load_time is not None:
            if file_mtime <= self._load_time:
                return self._context
        
        # Load the YAML file
        try:
            with open(self.context_path, 'r', encoding='utf-8') as f:
                self._context = yaml.safe_load(f)
                self._load_time = datetime.now()
                logger.info(f"Loaded financial context from {self.context_path}")
                return self._context
        except Exception as e:
            logger.error(f"Failed to load context: {e}")
            return {"error": str(e)}
    
    def get_full_context(self, section: Optional[str] = None) -> Dict:
        """
        Return the full financial context or a specific section.
        
        Args:
            section: Optional section name (people, accounts, properties, entities, etc.)
        
        Returns:
            Full context dict or specific section
        """
        context = self._load_context()
        
        if section and section in context:
            return {section: context[section]}
        
        return context
    
    def get_account_context(self, account_id: str) -> Dict:
        """
        Get context for a specific account.
        
        Returns account details including:
        - Account type and purpose
        - Linked property (if mortgage/offset)
        - Property details (if linked)
        - Linked loan details (for offset accounts)
        
        Args:
            account_id: The account ID to look up
            
        Returns:
            Account context dict with property and linked loan info
        """
        context = self._load_context()
        if "error" in context:
            return context
        
        accounts = context.get("accounts", [])
        properties = context.get("properties", [])
        
        # Find the account
        account = None
        for acc in accounts:
            if acc.get("account_id") == account_id:
                account = acc.copy()
                break
        
        if not account:
            return {"error": f"Account not found: {account_id}", "account_id": account_id}
        
        # If account has a property_id, include property details
        property_id = account.get("property_id")
        if property_id:
            for prop in properties:
                if prop.get("id") == property_id:
                    account["property"] = prop
                    break
        
        # If it's an offset account, include linked loan info
        linked_to = account.get("linked_to")
        if linked_to:
            for acc in accounts:
                if acc.get("account_id") == linked_to:
                    account["linked_loan"] = acc
                    break
        
        return account
    
    def get_property_context(self, property_id: str) -> Dict:
        """
        Get context for a specific property.
        
        Returns property details including:
        - Address and type
        - All linked accounts (mortgage, offset)
        
        Args:
            property_id: The property ID to look up
            
        Returns:
            Property context dict with linked accounts
        """
        context = self._load_context()
        if "error" in context:
            return context
        
        properties = context.get("properties", [])
        accounts = context.get("accounts", [])
        
        # Find the property
        property_info = None
        for prop in properties:
            if prop.get("id") == property_id:
                property_info = prop.copy()
                break
        
        if not property_info:
            return {"error": f"Property not found: {property_id}", "property_id": property_id}
        
        # Find all linked accounts
        linked_accounts = []
        for acc in accounts:
            if acc.get("property_id") == property_id:
                linked_accounts.append(acc)
        
        property_info["accounts"] = linked_accounts
        
        return property_info
    
    def resolve_entity(self, description: str) -> Optional[Dict]:
        """
        Try to match a transaction description to a known entity.
        
        Args:
            description: Transaction description to match
            
        Returns:
            Entity details if matched, None otherwise
        """
        context = self._load_context()
        if "error" in context:
            return None
        
        entities = context.get("entities", [])
        description_upper = description.upper()
        
        for entity in entities:
            aliases = entity.get("aliases", [])
            for alias in aliases:
                if alias.upper() in description_upper:
                    return entity
        
        return None
    
    def get_category_for_transaction(
        self,
        description: str,
        account_id: str,
        original_category: Optional[str] = None
    ) -> Optional[str]:
        """
        Apply category rules to determine the category for a transaction.
        
        Args:
            description: Transaction description
            account_id: Account ID
            original_category: Bank's original category
            
        Returns:
            Matched category or None if no rule matches
        """
        context = self._load_context()
        if "error" in context:
            return None
        
        rules = context.get("category_rules", [])
        account_context = self.get_account_context(account_id)
        account_type = account_context.get("type") if isinstance(account_context, dict) else None
        
        # Sort rules by priority (higher first)
        sorted_rules = sorted(rules, key=lambda r: r.get("priority", 0), reverse=True)
        
        for rule in sorted_rules:
            pattern = rule.get("pattern", "")
            conditions = rule.get("conditions", {})
            
            # Check if pattern matches description
            if pattern.upper() not in description.upper():
                continue
            
            # Check conditions
            conditions_met = True
            
            if "original_category" in conditions:
                if original_category != conditions["original_category"]:
                    conditions_met = False
            
            if "account_type" in conditions:
                if account_type != conditions["account_type"]:
                    conditions_met = False
            
            if conditions_met:
                return rule.get("category")
        
        return None
    
    def get_all_accounts_with_context(self) -> List[Dict]:
        """
        Get all accounts with their property context resolved.
        
        Returns:
            List of accounts with property details included
        """
        context = self._load_context()
        if "error" in context:
            return []
        
        accounts = context.get("accounts", [])
        result = []
        
        for acc in accounts:
            account_with_context = self.get_account_context(acc.get("account_id", ""))
            if "error" not in account_with_context:
                result.append(account_with_context)
        
        return result
