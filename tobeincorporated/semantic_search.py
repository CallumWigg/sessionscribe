import os
from sentence_transformers import SentenceTransformer, util
import torch
from termcolor import colored

# Load a pre-trained sentence transformer model
model = SentenceTransformer('all-MiniLM-L12-v2')  # or 'all-distilroberta-v1' for faster performance

def load_text_file(file_path):
    """Load a large text file and return the contents as a list of lines."""
    with open(file_path, 'r', encoding='utf-8') as file:
        lines = file.readlines()
    return lines

def embed_text(text_list, batch_size=64):
    """Convert a list of text to embeddings in batches for efficiency."""
    embeddings = []
    for i in range(0, len(text_list), batch_size):
        batch = text_list[i:i + batch_size]
        batch_embeddings = model.encode(batch, convert_to_tensor=True)
        embeddings.append(batch_embeddings)
    return torch.cat(embeddings)

def highlight_text(text, query, token_embeddings, query_embedding):
    """Highlight the most similar tokens or phrases within the given text."""
    tokens = text.split()
    highlighted_text = text
    for token in tokens:
        token_embedding = model.encode(token, convert_to_tensor=True)
        similarity = util.pytorch_cos_sim(token_embedding, query_embedding).item()
        if similarity > 0.5:  # Set a threshold for similarity
            highlighted_text = highlighted_text.replace(token, colored(token, 'red', attrs=['bold']))
    return highlighted_text

def truncate_text(text, query, max_length=150):
    """Truncate text to include the query or limit to max_length."""
    query_start = text.find(query)
    if query_start != -1:
        # If the query is found, center the snippet around it
        start = max(0, query_start - max_length // 2)
        end = min(len(text), query_start + len(query) + max_length // 2)
        snippet = text[start:end]
        if start > 0:
            snippet = "..." + snippet
        if end < len(text):
            snippet += "..."
    else:
        # If the query is not found, truncate to the first max_length characters
        snippet = text[:max_length] + ("..." if len(text) > max_length else "")
    return snippet

def semantic_search(query, document_embeddings, lines, top_k=5, min_score=0.2):
    """Perform semantic search to find the most similar sentences to the query."""
    # Encode the query
    query_embedding = model.encode(query, convert_to_tensor=True)

    # Compute cosine similarities between the query and the document
    cosine_scores = util.pytorch_cos_sim(query_embedding, document_embeddings)[0]

    # Get the top k highest scores
    top_results = torch.topk(cosine_scores, k=top_k)

    # Print the results with context and improved formatting
    results_shown = 0
    for score, idx in zip(top_results[0], top_results[1]):
        if score.item() < min_score:
            continue  # Skip results with a score below the minimum threshold
        
        idx = idx.item()
        
        if results_shown == 0:
            print("\nTop matching lines:")
        
        results_shown += 1
        
        # Display the score
        print(f"\nScore: {score.item():.4f}")
        
        # Truncate and display two lines before the matching line (if available)
        for i in range(max(0, idx-2), idx):
            line = truncate_text(lines[i].strip(), query)
            print(highlight_text(line, query, None, query_embedding))

        # Display the matching line with the query highlighted
        line = truncate_text(lines[idx].strip(), query)
        print(highlight_text(line, query, None, query_embedding))
        
        # Truncate and display two lines after the matching line (if available)
        for i in range(idx+1, min(len(lines), idx+3)):
            line = truncate_text(lines[i].strip(), query)
            print(highlight_text(line, query, None, query_embedding))

        # Stop if we've shown the top 5 results
        if results_shown >= top_k:
            break

def main():
    # Path to the massive text file
    file_path = 'C:\\Users\\callu\\OneDrive - Monash University\\DnD\\Session Recordings\\Curse of Strahd\\Curse of Strahd - Transcriptions.txt'

    # Load and embed the text
    lines = load_text_file(file_path)
    document_embeddings = embed_text(lines)

    while True:
        # Input query for semantic search
        query = input("Enter your search query (or type 'exit' to quit): ")
        if query.lower() == 'exit':
            break

        # Perform semantic search
        semantic_search(query, document_embeddings, lines)

if __name__ == "__main__":
    main()
