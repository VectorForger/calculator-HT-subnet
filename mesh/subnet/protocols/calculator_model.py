import re
import time
from typing import Dict, Any
from mesh.utils.logging import get_logger

logger = get_logger(__name__)

class SimpleCalculator:
    """Dead simple calculator - no async complexity"""
    
    def __init__(self):
        self.operation_count = 0
    
    def calculate(self, expression: str) -> Dict[str, Any]:
        """Calculate math expression - return simple dict"""
        try:
            # Clean the expression
            clean_expr = expression.replace(" ", "")
            
            # Simple validation - only allow safe characters
            safe_chars = set("0123456789+-*/.()") 
            if not all(c in safe_chars for c in clean_expr):
                return {
                    "success": False,
                    "error": "Invalid characters in expression"
                }
            
            # Do the math
            result = eval(clean_expr, {"__builtins__": {}})
            
            if not isinstance(result, (int, float)):
                return {
                    "success": False, 
                    "error": "Result is not a number"
                }
            
            self.operation_count += 1
            
            return {
                "success": True,
                "result": float(result)
            }
            
        except ZeroDivisionError:
            return {"success": False, "error": "Division by zero"}
        except Exception as e:
            return {"success": False, "error": str(e)}