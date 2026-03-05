import os
import re

def refactor_print_to_logging(src_dir):
    for root, dirs, files in os.walk(src_dir):
        if 'sandbox_workspace' in root or 'data' in root or '__pycache__' in root:
            continue
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Fast check if print( exists
                if 'print(' not in content:
                    continue

                lines = content.split('\n')
                new_lines = []
                import_added = False

                for line in lines:
                    # Very simple regex replace for print( -> logging.info(
                    # We only replace basic print statements
                    # and avoid multiline prints or print() without args for now unless simple
                    if re.search(r'^\s*print\(', line):
                        # Convert print(...) to logging.info(...)
                        new_line = re.sub(r'(^\s*)print\(', r'\1logging.info(', line)
                        new_lines.append(new_line)
                    else:
                        new_lines.append(line)
                        
                    # Inject import logging if needed
                    if not import_added and (line.startswith('import ') or line.startswith('from ')):
                        new_lines.insert(len(new_lines)-1, "import logging")
                        import_added = True

                # If no import statements were found, add at the top
                if not import_added and 'logging.info(' in '\n'.join(new_lines):
                    new_lines.insert(0, "import logging")
                    new_lines.insert(1, "logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')")
                elif 'logging.info(' in '\n'.join(new_lines):
                     new_lines.insert(2, "logging.basicConfig(level=logging.INFO, format='%(message)s')") # Simple format

                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(new_lines))
                print(f"Refactored {filepath}")

if __name__ == '__main__':
    refactor_print_to_logging('./src')
