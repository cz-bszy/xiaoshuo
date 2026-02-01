import re

path = r'e:\Test\xiaoshuo\SimpleMem\core\memory_builder.py'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_code = '''        if not isinstance(data, list):
            raise ValueError(f"Expected JSON array but got: {type(data)}")'''

new_code = '''        if not isinstance(data, list):
            # Auto-unwrap dict if LLM returned {"entries": [...]} or similar
            if isinstance(data, dict):
                for key in ["entries", "data", "results", "items", "memories", "memory_entries"]:
                    if key in data and isinstance(data[key], list):
                        data = data[key]
                        break
                else:
                    if len(data) == 1:
                        only_value = list(data.values())[0]
                        if isinstance(only_value, list):
                            data = only_value
            if not isinstance(data, list):
                raise ValueError(f"Expected JSON array but got: {type(data)}")'''

# Handle both LF and CRLF
old_code_crlf = old_code.replace('\n', '\r\n')
if old_code_crlf in content:
    content = content.replace(old_code_crlf, new_code.replace('\n', '\r\n'))
    print('Replaced with CRLF')
elif old_code in content:
    content = content.replace(old_code, new_code)
    print('Replaced with LF')
else:
    print('Pattern not found')
    exit(1)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('File updated successfully')
