# src/parser/parse_tree.py

class ParseTreeNode:
    def __init__(self, node_type, token=None, children=None):
        """
        A generic parse tree node.
        
        Args:
            node_type (str): The type of node (e.g., "binary", "literal", "identifier").
            token (dict or any): Optional token information (e.g., value, line, column).
            children (list): A list of child ParseTreeNode objects.
        """
        self.node_type = node_type  
        self.token = token  
        self.children = children if children is not None else []

    def __repr__(self):
        return f"ParseTreeNode({self.node_type}, {self.token}, {self.children})"
