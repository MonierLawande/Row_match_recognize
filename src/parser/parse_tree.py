class ParseTreeNode:
    def __init__(self, node_type, token=None, children=None):
        """
        A generic parse tree node.
        
        Args:
            node_type (str): The type of node (e.g., "binary", "literal", "identifier").
            token (dict): Optional token information (value, line, column, etc.).
            children (list): List of child ParseTreeNode objects.
        """
        self.node_type = node_type  
        self.token = token  
        self.children = children if children is not None else []

    def __repr__(self):
        return f"ParseTreeNode({self.node_type}, {self.token}, {self.children})"
