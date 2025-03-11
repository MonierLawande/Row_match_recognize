# My MATCH_RECOGNIZE Project

This project demonstrates how to parse SQL queries that include a MATCH_RECOGNIZE clause.  
The project is organized into several folders:
- **grammar**: Contains ANTLR-generated files.
- **parser**: Contains all parsing code (tokenization, ANTLR integration, expression & pattern parsing).
- **ast**: Contains AST definitions and builder code.
- **validator**: Contains semantic and structural validation logic.
- **tests**: Unit tests for each component.

See `main.py` for a usage example.
my_match_recognize_project/
├── README.md
├── requirements.txt
├── setup.py
├── main.py
├── src/
│   ├── __init__.py
│   ├── grammar/
│   │   ├── __init__.py
│   │   ├── TrinoLexer.py
│   │   ├── TrinoParser.py
│   │   ├── TrinoParserListener.py
│   │   └── TrinoParserVisitor.py
│   ├── parser/
│   │   ├── __init__.py
│   │   ├── antlr_parser.py
│   │   ├── expression_parser.py
│   │   └── pattern_parser.py
│   ├── ast/
│   │   ├── __init__.py
│   │   ├── expression_ast.py
│   │   ├── pattern_ast.py
│   │   ├── match_recognize_ast.py
│   │   └── ast_builder.py
│   └── validator/
│       ├── __init__.py
│       ├── semantic_validator.py
│       └── match_recognize_validator.py
└── tests/
    ├── __init__.py
    ├── test_parser.py
    ├── test_ast.py
    └── test_validator.py
