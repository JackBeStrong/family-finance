"""
Parser Factory with Auto-Registration

This module provides a flexible factory pattern for bank parsers:
- Auto-detection of bank format from CSV files
- Plugin-style registration of new parsers
- Support for custom parser configurations
- Batch processing of multiple files

Adding a new bank parser:
1. Create a new parser class extending BaseParser
2. Register it with ParserFactory.register()
3. Or place it in the parsers directory for auto-discovery
"""

from pathlib import Path
from typing import Dict, List, Optional, Type, Callable
import importlib
import pkgutil

from .base import BaseParser, Transaction


class ParserFactory:
    """
    Factory for creating and managing bank parsers.
    
    Supports:
    - Manual parser registration
    - Auto-detection of file format
    - Custom parser configurations
    - Batch processing
    """
    
    # Class-level registry of parsers
    _parsers: Dict[str, Type[BaseParser]] = {}
    _parser_instances: Dict[str, BaseParser] = {}
    
    @classmethod
    def register(cls, parser_class: Type[BaseParser], 
                 name: Optional[str] = None) -> Type[BaseParser]:
        """
        Register a parser class with the factory.
        
        Can be used as a decorator:
            @ParserFactory.register
            class MyBankParser(BaseParser):
                ...
        
        Or called directly:
            ParserFactory.register(MyBankParser, name='mybank')
        
        Args:
            parser_class: The parser class to register
            name: Optional name override (defaults to parser's bank_name)
            
        Returns:
            The parser class (for decorator usage)
        """
        # Create instance to get bank_name
        instance = parser_class()
        parser_name = name or instance.bank_name
        
        cls._parsers[parser_name] = parser_class
        cls._parser_instances[parser_name] = instance
        
        return parser_class
    
    @classmethod
    def unregister(cls, name: str) -> bool:
        """
        Unregister a parser by name.
        
        Args:
            name: The parser name to unregister
            
        Returns:
            True if parser was found and removed
        """
        if name in cls._parsers:
            del cls._parsers[name]
            del cls._parser_instances[name]
            return True
        return False
    
    @classmethod
    def get_parser(cls, name: str) -> Optional[BaseParser]:
        """
        Get a parser instance by name.
        
        Args:
            name: The bank name (e.g., 'westpac', 'anz')
            
        Returns:
            Parser instance or None if not found
        """
        return cls._parser_instances.get(name)
    
    @classmethod
    def get_parser_class(cls, name: str) -> Optional[Type[BaseParser]]:
        """
        Get a parser class by name.
        
        Args:
            name: The bank name
            
        Returns:
            Parser class or None if not found
        """
        return cls._parsers.get(name)
    
    @classmethod
    def list_parsers(cls) -> List[str]:
        """
        List all registered parser names.
        
        Returns:
            List of registered bank names
        """
        return list(cls._parsers.keys())
    
    @classmethod
    def detect_parser(cls, file_path: Path) -> Optional[BaseParser]:
        """
        Auto-detect the appropriate parser for a file.
        
        Tries each registered parser's can_parse() method.
        
        Args:
            file_path: Path to the CSV file
            
        Returns:
            Matching parser instance or None
        """
        file_path = Path(file_path)
        
        for name, parser in cls._parser_instances.items():
            try:
                if parser.can_parse(file_path):
                    return parser
            except Exception as e:
                # Log but continue trying other parsers
                print(f"Warning: Parser '{name}' failed detection check: {e}")
                continue
        
        return None
    
    @classmethod
    def parse_file(cls, file_path: Path, 
                   parser_name: Optional[str] = None) -> List[Transaction]:
        """
        Parse a file using auto-detection or specified parser.
        
        Args:
            file_path: Path to the CSV file
            parser_name: Optional parser name to use (skips auto-detection)
            
        Returns:
            List of parsed transactions
            
        Raises:
            ValueError: If no suitable parser found
        """
        file_path = Path(file_path)
        
        if parser_name:
            parser = cls.get_parser(parser_name)
            if not parser:
                raise ValueError(f"Unknown parser: {parser_name}")
        else:
            parser = cls.detect_parser(file_path)
            if not parser:
                raise ValueError(
                    f"Could not detect bank format for: {file_path}\n"
                    f"Registered parsers: {cls.list_parsers()}"
                )
        
        return parser.parse(file_path)
    
    @classmethod
    def parse_directory(cls, directory: Path, 
                        recursive: bool = True,
                        file_pattern: str = "*.csv") -> Dict[str, List[Transaction]]:
        """
        Parse all CSV files in a directory.
        
        Args:
            directory: Directory to scan
            recursive: Whether to scan subdirectories
            file_pattern: Glob pattern for files
            
        Returns:
            Dictionary mapping file paths to their transactions
        """
        directory = Path(directory)
        results = {}
        
        if recursive:
            files = directory.rglob(file_pattern)
        else:
            files = directory.glob(file_pattern)
        
        for file_path in files:
            try:
                transactions = cls.parse_file(file_path)
                results[str(file_path)] = transactions
            except ValueError as e:
                print(f"Skipping {file_path}: {e}")
            except Exception as e:
                print(f"Error parsing {file_path}: {e}")
        
        return results
    
    @classmethod
    def auto_discover_parsers(cls, package_name: str = "src.parsers") -> int:
        """
        Auto-discover and register parsers from a package.
        
        Scans the package for modules containing BaseParser subclasses.
        
        Args:
            package_name: The package to scan
            
        Returns:
            Number of parsers discovered
        """
        count = 0
        
        try:
            package = importlib.import_module(package_name)
        except ImportError:
            return 0
        
        for importer, modname, ispkg in pkgutil.iter_modules(package.__path__):
            if modname.startswith('_') or modname in ('base', 'factory'):
                continue
            
            try:
                module = importlib.import_module(f"{package_name}.{modname}")
                
                # Find BaseParser subclasses in the module
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (isinstance(attr, type) and 
                        issubclass(attr, BaseParser) and 
                        attr is not BaseParser):
                        
                        # Check if already registered
                        instance = attr()
                        if instance.bank_name not in cls._parsers:
                            cls.register(attr)
                            count += 1
                            
            except Exception as e:
                print(f"Warning: Failed to load parser module '{modname}': {e}")
        
        return count


def register_default_parsers():
    """Register the built-in parsers."""
    from .westpac import WestpacParser
    from .anz import ANZParser
    from .bankwest import BankwestParser
    from .cba import CBAParser
    from .macquarie import MacquarieParser
    
    ParserFactory.register(WestpacParser)
    ParserFactory.register(ANZParser)
    ParserFactory.register(BankwestParser)
    ParserFactory.register(CBAParser)
    ParserFactory.register(MacquarieParser)


# Auto-register default parsers when module is imported
register_default_parsers()
