from typing import Set, Tuple, Any

class MathSafetyError(Exception):
    pass

POSITIVE_FIELDS = {"close", "open", "high", "low", "vwap", "amount", "volume"}

class MathSafetyVisitor:
    def __init__(self, approved_operators: Set[str]):
        self.approved_operators = approved_operators
        self.used_operators: Set[str] = set()
        self.used_fields: Set[str] = set()
        self.bare_identifiers: Set[str] = set()

    def check(self, node: Any):
        self.visit(node)

    def visit(self, node: Any) -> Tuple[bool, bool]:
        """
        Traverses the Qlib AST and returns domain properties (can_be_zero, can_be_negative).
        """
        if isinstance(node, (int, float)):
            return node == 0, node < 0
            
        node_type = type(node).__name__
        
        if node_type in ("Feature", "PFeature"):
            name = getattr(node, "name", getattr(node, "_name", str(node)))
            self.used_fields.add(f"${name}")
            if name.lower() in POSITIVE_FIELDS:
                return False, False
            return True, True
            
        # Record operator usage
        self.used_operators.add(node_type)
        
        # Traverse children
        if hasattr(node, "condition"):
            self.visit(node.condition)
            
        lz, ln = None, None
        rz, rn = None, None
        z, n = None, None
        
        if hasattr(node, "feature_left"):
            lz, ln = self.visit(node.feature_left)
        if hasattr(node, "feature_right"):
            rz, rn = self.visit(node.feature_right)
        if hasattr(node, "feature"):
            z, n = self.visit(node.feature)
            
        if node_type in ("Div", "Mod"):
            if rz is not None and rz:
                 raise MathSafetyError(f"Possible division by zero detected in operator '{node_type}'.")
            if (lz is not None and not lz and not ln) and (rz is not None and not rz and not rn):
                 return False, False
            return True, True
            
        elif node_type == "Add":
            if (lz is not None and not ln) and (rz is not None and not rn):
                cz = (lz and rz)
                return cz, False
            return True, True
            
        elif node_type == "Sub":
            return True, True
            
        elif node_type == "Mul":
            if (lz is not None and not ln and not lz) and (rz is not None and not rn and not rz):
                return False, False
            cz = (lz or rz) if (lz is not None and rz is not None) else True
            return cz, True
            
        elif node_type == "Power":
            return True, True
            
        elif node_type == "Log":
            if z is not None and (z or n):
                raise MathSafetyError("Log() operand must be strictly positive to avoid domain errors (Log(0) or Log(-x)). Trap it with Max() or Abs()+1.")
            return True, True
            
        elif node_type == "Sqrt":
            if n is not None and n:
                raise MathSafetyError("Sqrt() operand must be non-negative.")
            return True, True
            
        elif node_type == "Abs":
            if z is not None: return z, False
            return True, False
            
        elif node_type == "Max":
            if lz is not None and rz is not None:
                cn = ln and rn
                cz = (lz and rz) or (lz and rn) or (rz and ln)
                if (not lz and not ln) or (not rz and not rn):
                    cz, cn = False, False
                return cz, cn
            return True, True
            
        elif node_type in ("Mean", "EMA", "WMA", "Ts_Mean", "Ref", "Sum", "Ts_Sum", "Max", "Min", "Ts_Max", "Ts_Min", "If"):
            if node_type == "If" and lz is not None and rz is not None:
                return (lz or rz), (ln or rn)
            if z is not None: return z, n
            if lz is not None: return lz, ln
            
        return True, True


def parse_and_check_ast(formula: str, approved_operators: Set[str], allowed_fields: Set[str]) -> Tuple[Set[str], Set[str], Set[str]]:
    """
    Parses the formula using Qlib's true AST loader to guarantee SSOT.
    Returns: (invalid_ops, invalid_fields, bare_identifiers)
    Raises ValueError on syntax error, MathSafetyError on domain violation.
    """
    from qlib.data.data import parse_field
    from qlib.data.base import Feature, PFeature
    import qlib.data.ops
    
    class Operators:
        pass
    
    # Inject Qlib's known operators into our sandbox
    for name in dir(qlib.data.ops):
        if not name.startswith("_"):
            setattr(Operators, name, getattr(qlib.data.ops, name))
            
    try:
        parsed_str = parse_field(formula)
        ast = eval(parsed_str, {"__builtins__": None}, {
            "Operators": Operators, 
            "Feature": Feature, 
            "PFeature": PFeature
        })
    except Exception as e:
        raise ValueError(f"Qlib AST parsing failed (syntax or unrecognized token): {e}")
        
    visitor = MathSafetyVisitor(approved_operators)
    visitor.check(ast)
    
    invalid_ops = visitor.used_operators - approved_operators
    invalid_fields = visitor.used_fields - allowed_fields
    
    # Since Qlib's parser replaces unknown tokens contextually or raises error, bare_identifiers is largely mitigated.
    # However we return it for compatibility.
    return invalid_ops, invalid_fields, visitor.bare_identifiers
