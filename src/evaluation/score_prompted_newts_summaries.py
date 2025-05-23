'''
score_prompted_newts_summaries.py

This script scores the NEWTS summaries generated by the prompted model.
'''

# Standard library imports
import os
import json
import logging
from typing import Dict, Any, Optional # Added Optional

from src.evaluation.scorer import Scorer

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def score_newts_summaries(input_file_path: str) -> Optional[Dict[str, Any]]:
    """
    Loads generated summaries from a JSON file, scores each unique summary 
    (identified by its prompt strategy key like "neutral", "topic_tid1_encouraged", etc.) 
    using the Scorer, and returns a dictionary containing the original data 
    plus the scores in a flattened structure suitable for plotting.

    Input JSON structure assumption:
    - 'experiment_information': {...}
    - 'generated_summaries': {
        "article_idx_str": {
            "original_summary1": "...", "original_summary2": "...",
            "tid1": ..., "tid2": ...,
            "summaries": { // Nested by behavior_name
                "topic": {
                    "neutral": {"summary": "text...", ...}, // variation_key
                    "topic_tid1_encouraged": {"summary": "text...", ...}
                },
                "sentiment": {
                    "neutral": {"summary": "text...", ...}, // Same neutral summary text
                    "sentiment_positive_encouraged": {"summary": "text...", ...}
                }
                // ... other behaviors
            }
        }
    }

    Output 'scored_summaries' structure for each article_idx_str:
    {
        "neutral": {score_dict_for_the_one_neutral_summary}, // Globally unique prompt strategy key
        "topic_tid1_encouraged": {score_dict_for_topic_tid1_summary},
        "sentiment_positive_encouraged": {score_dict_for_sentiment_positive_summary},
        // ... and so on for all unique prompt strategies.
        // Each score_dict here should contain the full set of scores (sentiment, intrinsic, topic, etc.)
    }

    Args:
        input_file_path (str): The path to the input JSON file.

    Returns:
        Optional[Dict[str, Any]]: A dictionary containing the original data and 
                                 a new 'scored_summaries' key.
                                 Returns None on critical errors.
    """

    logger.info(f"Starting scoring process for file: {input_file_path}")

    # --- 1. Initialize Scorer ---
    try:
        # Ensure Scorer is accessible. If it's in a different relative path, adjust.
        # from ..evaluation.scorer import Scorer # Example if it's one level up then in evaluation
        scorer = Scorer() 
        logger.info("Scorer initialized successfully.")
    except ImportError:
        logger.error("Failed to import Scorer. Please ensure 'src.evaluation.scorer' is correct and in PYTHONPATH.")
        return None
    except Exception as e:
        logger.error(f"Fatal Error: Failed to initialize the Scorer: {e}", exc_info=True)
        return None

    # --- 2. Load Input Data ---
    try:
        with open(input_file_path, 'r', encoding='utf-8') as f:
            input_data = json.load(f)
        logger.info(f"Successfully loaded data from {input_file_path}")

        if 'experiment_information' not in input_data or 'generated_summaries' not in input_data:
            logger.error("Input JSON is missing required keys: 'experiment_information' or 'generated_summaries'")
            return None
        if not isinstance(input_data['generated_summaries'], dict):
            logger.error("'generated_summaries' should be a dictionary. Found type: %s", type(input_data['generated_summaries']))
            return None
            
    except FileNotFoundError:
        logger.error(f"Input file not found: {input_file_path}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON from file: {input_file_path} - {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred while reading the input file: {e}", exc_info=True)
        return None

    # --- 3. Prepare Output Structure ---
    output_data = {
        'experiment_information': input_data['experiment_information'],
        'generated_summaries': input_data['generated_summaries'], # Keep original generated summaries
        'scored_summaries': {}  # This will hold the new flattened structure
    }

    # --- 4. Iterate and Score ---
    total_articles = len(input_data['generated_summaries'])
    processed_articles_count = 0
    logger.info(f"Starting to score summaries for {total_articles} articles.")

    for article_idx_str, article_content in input_data['generated_summaries'].items():
        processed_articles_count += 1
        logger.info(f"Processing article {processed_articles_count}/{total_articles} (ID: {article_idx_str})")
        
        # This will store scores directly keyed by the unique prompt strategy variation_key
        flat_article_scores: Dict[str, Optional[Dict[str, Any]]] = {} 
        processed_neutral_for_this_article = False # To score "neutral" only once per article

        # Extract article-level metadata needed for scoring all its summaries
        tid1 = article_content.get('tid1')
        tid2 = article_content.get('tid2')
        ref1 = article_content.get('original_summary1')
        ref2 = article_content.get('original_summary2')
        
        summaries_by_behavior = article_content.get('summaries', {})

        if not isinstance(summaries_by_behavior, dict):
            logger.warning(f"Article {article_idx_str}: 'summaries' field is not a dictionary. Skipping scoring for this article.")
            output_data['scored_summaries'][article_idx_str] = {} # Assign empty dict for this article
            continue

        # Iterate through all summaries to flatten them by their unique variation_key
        for behavior_name, variations_dict in summaries_by_behavior.items():
            if not isinstance(variations_dict, dict):
                logger.warning(f"Article {article_idx_str}, Behavior {behavior_name}: Value is not a dictionary of variations. Skipping this behavior group.")
                continue

            for variation_key, prompt_and_summary_dict in variations_dict.items():
                # variation_key examples: "neutral", "topic_tid1_encouraged", "sentiment_positive_encouraged"
                
                # Handle "neutral" summaries: score only the first valid encounter per article
                if variation_key == "neutral":
                    if processed_neutral_for_this_article:
                        logger.debug(f"Article {article_idx_str}: 'neutral' summary already processed and scored. Skipping redundant entry under behavior '{behavior_name}'.")
                        continue 
                    # If not processed, it will be handled like any other key below.
                    # We'll mark it as processed *after* successful scoring.
                
                # If this specific variation_key (e.g. "topic_tid1_encouraged") has already been placed in flat_article_scores, skip.
                # This handles cases where a non-"neutral" key might somehow appear under multiple behavior groups.
                if variation_key != "neutral" and variation_key in flat_article_scores:
                    logger.warning(f"Article {article_idx_str}: Variation key '{variation_key}' encountered again under behavior '{behavior_name}'. Already processed. Check input data generation.")
                    continue

                if not isinstance(prompt_and_summary_dict, dict):
                    logger.warning(f"Article {article_idx_str}, Behavior {behavior_name}, Variation {variation_key}: Value is not a dictionary. Skipping.")
                    if variation_key not in flat_article_scores: # Avoid overwriting a successfully scored neutral
                         flat_article_scores[variation_key] = None 
                    continue

                generated_text = prompt_and_summary_dict.get('summary')

                if not isinstance(generated_text, str):
                    logger.warning(f"Article {article_idx_str}, Behavior {behavior_name}, Variation {variation_key}: Generated text is not a string ('{type(generated_text)}'). Skipping.")
                    if variation_key not in flat_article_scores:
                        flat_article_scores[variation_key] = None
                    continue
                 
                # Score the summary text
                try:
                    logger.debug(f"Scoring for Article {article_idx_str}, Strategy Key '{variation_key}' (found under Behavior '{behavior_name}')")
                    score_dict = scorer.score_individual_text(
                        text=generated_text,
                        tid1=tid1,
                        tid2=tid2,
                        reference_text1=ref1,
                        reference_text2=ref2
                        # Assuming Scorer's default arguments for topic_method, distinct_n are fine
                    )
                    flat_article_scores[variation_key] = score_dict
                    if variation_key == "neutral": # Mark neutral as processed only after successful scoring
                        processed_neutral_for_this_article = True


                except Exception as e:
                    logger.error(f"Error scoring Article {article_idx_str}, Strategy Key '{variation_key}': {e}", exc_info=False) # Set exc_info=True for more details if needed
                    if variation_key not in flat_article_scores: # Avoid overwriting successfully scored neutral
                        flat_article_scores[variation_key] = None 
            
        output_data['scored_summaries'][article_idx_str] = flat_article_scores

    logger.info(f"Finished scoring all articles. Results generated for {len(output_data['scored_summaries'])} articles.")
    return output_data

def main() -> None:
    """
    This function scores the NEWTS summaries generated by the prompted model.
    """
    # load results and scores paths from environment variables
    results_path = os.getenv('NEWTS_SUMMARIES_PATH')
    scores_path = os.getenv('SCORES_PATH')
    file_path = 'prompt_engineering/prompt_engineering_summaries_llama3_3b_NEWTS_train_250_articles_20250518_030833.json'
    input_json_path = os.path.join(results_path, file_path)

    scored_summaries = score_newts_summaries(input_json_path)

    # Save the scored summaries to a new JSON file
    output_json_path = os.path.join(scores_path, file_path)
    with open(output_json_path, 'w', encoding='utf-8') as f:
        json.dump(scored_summaries, f, ensure_ascii=False, indent=2)

    logger.info(f"Successfully saved scored summaries to {output_json_path}")
if __name__ == '__main__':
    main()
