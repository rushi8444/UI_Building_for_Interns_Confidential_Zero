import json

with open(r'C:\Users\ADMIN\.gemini\antigravity-ide\brain\b0ca2ecc-e099-4395-8153-4944fe1bd5be\.system_generated\logs\transcript_full.jsonl', 'r', encoding='utf-8') as f:
    with open('out.txt', 'w', encoding='utf-8') as out:
        for line in f:
            data = json.loads(line)
            if 'content' in data:
                if '0x1188' in data['content'] and 'TakionL2Quote' in data['content']:
                    out.write(data['content'] + '\n')
            if 'tool_calls' in data:
                for tc in data['tool_calls']:
                    if tc['name'] == 'write_to_file':
                        out.write(tc['args']['TargetFile'] + '\n' + tc['args']['CodeContent'] + '\n---\n')
                    elif tc['name'] == 'replace_file_content' or tc['name'] == 'multi_replace_file_content':
                        out.write(tc['args']['TargetFile'] + '\n' + str(tc['args']) + '\n---\n')
