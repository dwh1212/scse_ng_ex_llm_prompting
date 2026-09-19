## Import the necessary modules
import json
import os
import sys

import ollama

## Import the function from the module parse_data
from parse_data import load_items, get_unclaimed_items, save_result

## Name of the Qwen model served by the local Ollama instance.
## Override with the environment variable QWEN_MODEL if a different tag is installed.
QWEN_MODEL = os.environ.get("QWEN_MODEL", "qwen2.5:1.5b")

## Path to the lost-and-found database and to the output result file.
DATA_FILE = "found_items.json"
OUTPUT_FILE = os.path.join("output", "match_result.json")


## Build your prompt based on the description the user provides 
## and the items that are available in the lost-and-found database.
## The model must follow the rules listed in the README file
## The function should return the system prompt and the user prompt.
## You may need to use json.dumps() to convert the available_items list into a JSON string.
def build_prompt(description, available_items):
    system_prompt = (
        "You are an assistant for a campus lost-and-found system. "
        "Your only job is to find possible matches for a lost item using "
        "ONLY the items listed in the user-provided JSON database.\n\n"
        "Rules:\n"
        "- Use only the given JSON data. Never invent or guess items that are not in it.\n"
        "- Not all details of an item need to match for it to be a possible match "
        "(e.g. a missing color or location is still a candidate).\n"
        '- An item is a possible match only if its "item" type is the same as, or '
        "very similar to, the type of the lost item (e.g. backpack = bag, "
        "water bottle = thermos/flask, headphones = earphones, laptop charger = "
        "charger). If the item type is different, it is NOT a possible match, "
        "even if the color or location matches.\n"
        '- If NO item in the database plausibly matches the lost item, "matches" '
        "must be an empty list [].\n"
        '- "confidence" must be exactly one of: LOW, MEDIUM, HIGH. '
        "HIGH = strong match on item type and most details; "
        "MEDIUM = partial match; LOW = weak or uncertain match.\n"
        "- Reply with ONLY a JSON object, with exactly this structure:\n"
        '  {"matches": ["ITEM_ID"], "confidence": "LOW"}\n'
        '- "matches" must contain ALL possible matching item IDs.\n'
        "- Do not include any explanation or text outside the JSON object.\n\n"
        "Examples:\n"
        '- Lost item: "I lost my phone charger". Database: '
        '[{"id":"F104","item":"laptop charger","color":"black","location":"Computer Lab","date":"2026-09-17"}]. '
        'Correct output: {"matches": ["F104"], "confidence": "MEDIUM"}\n'
        '- Lost item: "I lost a pink unicorn plush toy". Database: '
        '[{"id":"F101","item":"backpack","color":"black","location":"Library 2nd floor","date":"2026-09-15"}]. '
        'Correct output: {"matches": [], "confidence": "LOW"}\n'
        '- Lost item: "I lost a black backpack". Database: '
        '[{"id":"F101","item":"backpack","color":"black","location":"Library 2nd floor","date":"2026-09-15"}, '
        '{"id":"F104","item":"laptop charger","color":"black","location":"Computer Lab","date":"2026-09-17"}]. '
        'Correct output: {"matches": ["F101"], "confidence": "MEDIUM"} (F104 is a charger, not a backpack).'
    )
    user_prompt = (
        "Lost item description: " + description + "\n\n"
        "Available lost-and-found items (JSON):\n" + json.dumps(available_items, ensure_ascii=False)
    )
    return system_prompt, user_prompt


## Logic to ask Qwen for all the possible matches based on the system prompt and user prompt.
## The function should return the response from Qwen.
def ask_qwen(system_prompt, user_prompt):
    response = ollama.chat(
        model=QWEN_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        options={"temperature": 0},
    )
    return response["message"]["content"]


## Logic to parse the response from Qwen and return the result. 
## You may need to use json.loads() to convert the response string into a suitable Python data structure.
def parse_response(response_text):
    text = response_text.strip()
    # Strip markdown code fences if the model wrapped the JSON in them.
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    # Keep only the JSON object if the model added extra text around it.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]
    return json.loads(text)


## Logic to validate the result returned by Qwen.
## It should check if the result is a dictionary, contains the keys "matches" and "confidence", and that the values are of the correct type.
## If everything is correct, then it should check if the item IDs in the "matches" list are valid IDs .
def validate_result(result, available_items):
    if not isinstance(result, dict):
        return False
    if "matches" not in result or "confidence" not in result:
        return False

    matches = result["matches"]
    confidence = result["confidence"]

    if not isinstance(matches, list):
        return False
    if not all(isinstance(match_id, str) for match_id in matches):
        return False
    if confidence not in ("LOW", "MEDIUM", "HIGH"):
        return False

    valid_ids = {item["id"] for item in available_items}
    return all(match_id in valid_ids for match_id in matches)


## Logic to display the matches found by Qwen in a user-friendly format.
## It should look something like this:
""" 
CAMPUS LOST-AND-FOUND ASSISTANT
==================================================

Describe the item you lost: I lost a black bag somewhere

Searching for possible matches...

MATCH RESULT
--------------------------------------------------
Confidence: MEDIUM

Possible matches:

ID: F101
Item: backpack
Color: black
Location: Library 2nd floor
Date found: 2026-09-15

Result saved to output/match_result.json
 """
## If no matches are found, it should display a message indicating that no matches were found, along with the empty list
def display_matches(result, available_items):
    matches = result.get("matches", [])
    confidence = result.get("confidence", "LOW")

    print("MATCH RESULT")
    print("-" * 50)
    print("Confidence:", confidence)
    print()

    if not matches:
        print("No matches were found. Possible matches: []")
        return

    items_by_id = {item["id"]: item for item in available_items}
    print("Possible matches:")
    print()
    for match_id in matches:
        item = items_by_id.get(match_id)
        if item is None:
            continue
        print("ID:", item["id"])
        print("Item:", item["item"])
        print("Color:", item["color"])
        print("Location:", item["location"])
        print("Date found:", item["date"])
        print()


## Control center for the entire program.
def main():
    print("CAMPUS LOST-AND-FOUND ASSISTANT")
    print("=" * 50)
    print()

    description = input("Describe the item you lost: ").strip()
    print()
    print("Searching for possible matches...")
    print()

    items = load_items(DATA_FILE)
    available_items = get_unclaimed_items(items)

    system_prompt, user_prompt = build_prompt(description, available_items)

    try:
        response_text = ask_qwen(system_prompt, user_prompt)
    except Exception as e:
        print(f"ERROR: Could not reach the Ollama server ({e}).")
        print("Make sure Ollama is running and the model '" + QWEN_MODEL + "' has been pulled.")
        sys.exit(1)

    try:
        result = parse_response(response_text)
    except json.JSONDecodeError:
        print("ERROR: The model response was not valid JSON.")
        print("Raw response:", response_text)
        sys.exit(1)

    if not validate_result(result, available_items):
        print("ERROR: The model returned an invalid result.")
        print("Result:", result)
        sys.exit(1)

    display_matches(result, available_items)

    save_result(result, OUTPUT_FILE)
    print(f"Result saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
