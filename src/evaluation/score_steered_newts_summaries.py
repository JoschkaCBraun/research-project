'''
score_steered_newts_summaries.py

This script scores the steered NEWTS summaries generated by the steered NEWTS model.
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
    Loads generated summaries from a JSON file, scores each summary using the Scorer,
    and returns a dictionary containing the original data plus the scores.

    Assumes the input JSON file has 'experiment_information' and 
    'generated_summaries' keys. 'generated_summaries' is expected to be a 
    dictionary keyed by stringified article_idx.

    Args:
        input_file_path (str): The path to the input JSON file.

    Returns:
        Optional[Dict[str, Any]]: A dictionary containing the original data and 
                                 a new 'scored_summaries' key with the scoring results.
                                 Returns None if the input file cannot be read or parsed,
                                 or if the Scorer fails to initialize.
    """
    logger.info(f"Starting scoring process for file: {input_file_path}")

    # --- 1. Initialize Scorer ---
    try:
        scorer = Scorer() 
        logger.info("Scorer initialized successfully.")
    except Exception as e:
        logger.error(f"Fatal Error: Failed to initialize the Scorer: {e}", exc_info=True)
        return None

    # --- 2. Load Input Data ---
    try:
        with open(input_file_path, 'r', encoding='utf-8') as f:
            input_data = json.load(f)
        logger.info(f"Successfully loaded data from {input_file_path}")

        # Basic validation of expected keys
        if 'experiment_information' not in input_data or 'generated_summaries' not in input_data:
            logger.error("Input JSON is missing required keys: 'experiment_information' or 'generated_summaries'")
            return None
        if not isinstance(input_data['generated_summaries'], dict):
            logger.error("'generated_summaries' should be a dictionary keyed by article_idx (as string). Found type: %s", type(input_data['generated_summaries']))
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
        'generated_summaries': input_data['generated_summaries'],
        'scored_summaries': {}  # Initialize empty dict for scores
    }

    # --- 4. Iterate and Score ---
    total_articles = len(input_data['generated_summaries'])
    processed_articles = 0
    logger.info(f"Starting to score summaries for {total_articles} articles.")

    for article_idx_str, article_data in input_data['generated_summaries'].items():
        processed_articles += 1
        logger.info(f"Processing article {processed_articles}/{total_articles} (ID: {article_idx_str})")
        
        article_scores: Dict[str, Optional[Dict[str, Any]]] = {} # Scores for this article

        # Extract necessary info (handle potential missing keys gracefully)
        tid1 = article_data.get('tid1')
        tid2 = article_data.get('tid2')
        ref1 = article_data.get('summary1')
        ref2 = article_data.get('summary2')
        summaries_to_score = article_data.get('summaries', {})

        if not isinstance(summaries_to_score, dict):
            logger.warning(f"Article {article_idx_str}: 'summaries' field is not a dictionary. Skipping scoring for this article.")
            output_data['scored_summaries'][article_idx_str] = None # Mark article as unscorable
            continue

        for strength_str, generated_text in summaries_to_score.items():
            if not isinstance(generated_text, str):
                 logger.warning(f"Article {article_idx_str}, Strength {strength_str}: Generated text is not a string ('{type(generated_text)}'). Skipping scoring for this summary.")
                 article_scores[strength_str] = None
                 continue
                 
            try:
                # Call the scorer's method for individual text scoring
                # Rely on default arguments within score_individual_text for 
                # topic_method and distinct_n
                score_dict = scorer.score_individual_text(
                    text=generated_text,
                    tid1=tid1,
                    tid2=tid2,
                    reference_text1=ref1,
                    reference_text2=ref2
                    # No topic_method or distinct_n passed here
                )
                article_scores[strength_str] = score_dict

            except Exception as e:
                logger.error(f"Error scoring article {article_idx_str}, strength {strength_str}: {e}", exc_info=False)
                article_scores[strength_str] = None

        output_data['scored_summaries'][article_idx_str] = article_scores

    logger.info(f"Finished scoring all articles. Results generated for {len(output_data['scored_summaries'])} articles.")
    return output_data

def main() -> None:
    # load results and scores paths from environment variables
    results_path = os.getenv('NEWTS_SUMMARIES_PATH')
    scores_path = os.getenv('SCORES_PATH')
    file_path = 'toxicity_vectors_with_prompts/toxicity_summaries_llama3_3b_NEWTS_test_100_articles_words_20250515_155443.json'

    input_json_path = os.path.join(results_path, file_path)

    scored_summaries = score_newts_summaries(input_json_path)

    # Save the scored summaries to a new JSON file
    output_json_path = os.path.join(scores_path, file_path)
    with open(output_json_path, 'w', encoding='utf-8') as f:
        json.dump(scored_summaries, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
