import csv
import random
from pathlib import Path

random.seed(7)

things = ["sales", "orders", "customers", "products", "revenue", "employees",
          "invoices", "payments", "students", "inventory", "tickets", "expenses"]
fields = ["city", "category", "status", "month", "region", "department", "price", "date"]
aggs = ["total", "average", "count of", "number of", "sum of", "maximum", "minimum"]

sql_templates = [
    "What is the {agg} {thing}?",
    "Show me {thing} by {field}",
    "{agg} {thing} per {field}",
    "Which {field} has the most {thing}?",
    "Top 5 {thing} by {field}",
    "List all {thing} where {field} is {val}",
    "How many {thing} were there last month?",
    "Give me {thing} grouped by {field}",
    "Compare {thing} across each {field}",
    "What was the {agg} {thing} in 2025?",
    "Find {thing} with the highest {field}",
    "Break down {thing} by {field} and month",
    "Which customers bought the most {thing}?",
    "Show {thing} trend over time",
]
dataset_templates = [
    "What columns are in the {thing} table?",
    "What does the {field} column mean?",
    "Describe the {thing} table",
    "How are {thing} and customers connected?",
    "What type is the {field} column?",
    "Is there a {field} column anywhere?",
    "Which table has {field}?",
]
dataset_fixed = [
    "What tables do I have?", "What data did I upload?", "Explain my dataset",
    "How many tables are there?", "Give me an overview of the data",
    "What can I ask about this data?", "Which tables are related?",
    "Summarise the schema", "What files did I upload?", "What is in this dataset?",
    "Show me the structure of my data", "List the tables and columns",
]
small_talk = [
    "hi", "hello", "hey there", "good morning", "thanks", "thank you so much",
    "ok", "cool", "great, thanks", "bye", "see you", "how are you?",
    "who are you?", "what can you do?", "nice", "awesome", "you're helpful",
    "good evening", "hello TableTalk", "thanks a lot", "that's perfect",
    "hmm okay", "sounds good", "got it", "can you help me?", "what's your name?",
    "nice to meet you", "lol", "wow", "brilliant", "cheers", "alright",
]
off_topic = [
    "What's the weather today?", "Tell me a joke", "Who won the cricket match?",
    "Write me a poem", "What is the capital of France?", "Book a flight to Delhi",
    "Recommend a movie", "How do I cook pasta?", "What's the latest news?",
    "Translate hello into Spanish", "Who is the president of the USA?",
    "Write an email to my boss", "What is the meaning of life?",
    "Help me with my maths homework", "What time is it in London?",
    "Explain quantum physics", "Give me workout tips", "What's the stock price of Apple?",
    "Play some music", "Write Python code for a game", "Who is Shah Rukh Khan?",
    "How do I lose weight?", "What should I name my dog?", "Plan my trip to Goa",
    "Tell me about World War 2", "What's a good laptop to buy?",
    "How do vaccines work?", "Write a story about dragons", "What is bitcoin?",
    "Fix my wifi", "Summarise this news article", "Who invented the telephone?",
]


def fill(t):
    return t.format(agg=random.choice(aggs), thing=random.choice(things),
                    field=random.choice(fields), val=random.choice(["Mumbai", "Pending", "2025"]))


rows = []
rows += [(fill(random.choice(sql_templates)), "sql") for _ in range(90)]
rows += [(fill(random.choice(dataset_templates)), "dataset") for _ in range(50)] + \
        [(q, "dataset") for q in dataset_fixed]
rows += [(q, "small_talk") for q in small_talk]
rows += [(q, "off_topic") for q in off_topic]
rows = list(dict.fromkeys(rows))  # drop duplicates
random.shuffle(rows)

out = Path("training/router_examples.csv")
out.parent.mkdir(exist_ok=True)
with out.open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["text", "intent"])
    w.writerows(rows)
print(f"Wrote {len(rows)} examples to {out}")