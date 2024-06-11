import json

# Paths to the input and output JSON files
input_file_path = 'Json_Files/company_info.json'
output_file_path = 'Json_Files/company_info_transformed.json'

# Read the JSON data from the file
with open(input_file_path, 'r', encoding='utf-8') as file:
    data = json.load(file)

# Transform the data
for entry in data:
    entry["addresses"] = f"{entry.pop('street')}, {entry.pop('city')}"

for entry in data:
    entry["company_name"] = [entry.pop('name')]

# Write the transformed data back to a new JSON file
with open(output_file_path, 'w', encoding='utf-8') as file:
    json.dump(data, file, indent=4, ensure_ascii=False)

print(f"Transformed data has been saved to {output_file_path}")
