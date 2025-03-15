from src.parser.antlr_parser import parse_input

def extract_match_recognize_pattern(parse_tree, parser):
    """Extract the pattern from a MATCH_RECOGNIZE clause in the parse tree"""
    def find_pattern_node(node):
        """Recursively search for the PATTERN node and extract its content"""
        if not node or not hasattr(node, 'getChildCount'):
            return None
            
        # Check if this is a pattern node
        if hasattr(node, 'PATTERN') and node.PATTERN():
            # Loop through children to find the rowPattern node
            for i in range(node.getChildCount()):
                child = node.getChild(i)
                if hasattr(child, 'rowPattern'):
                    return child.rowPattern()
        
        # Recursively search children
        for i in range(node.getChildCount()):
            result = find_pattern_node(node.getChild(i))
            if result:
                return result
        
        return None

    # Find the pattern node
    pattern_node = find_pattern_node(parse_tree)
    
    if pattern_node:
        # Extract the pattern text
        return pattern_node.getText().strip('()')
    
    return None

def extract_match_recognize_details(parse_tree, parser):
    """Extract all details from a MATCH_RECOGNIZE clause"""
    # Find patternRecognition node
    def find_pattern_recognition_node(node):
        if not node or not hasattr(node, 'getChildCount'):
            return None
        
        # Check node type using rule name if possible
        if hasattr(node, 'getRuleIndex') and node.getRuleIndex() >= 0:
            rule_name = parser.ruleNames[node.getRuleIndex()]
            if rule_name == 'patternRecognition':
                return node
                
        # Recursively check children
        for i in range(node.getChildCount()):
            result = find_pattern_recognition_node(node.getChild(i))
            if result:
                return result
                
        return None

    pattern_recognition = find_pattern_recognition_node(parse_tree)
    
    if not pattern_recognition:
        return {"error": "No patternRecognition node found"}
    
    result = {
        "pattern": "",
        "partition_by": [],
        "order_by": [],
        "measures": [],
        "define_clauses": []
    }
    
    # Extract pattern
    pattern = extract_match_recognize_pattern(pattern_recognition, parser)
    if pattern:
        result["pattern"] = pattern
    
    # Extract other clauses (simplified for brevity)
    # Implementation would follow similar pattern as above
    
    return result
