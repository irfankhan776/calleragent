def detect_sentiment(transcript: str) -> str:
    if not transcript:
        return "Neutral"
        
    text = transcript.lower()
    
    positive_keywords = [
        "interested", "yes", "sure", "sounds good", "tell me more", 
        "great", "absolutely", "perfect", "love it", "when can", "let's do it"
    ]
    
    negative_keywords = [
        "not interested", "don't call", "busy", "no thanks", "remove", 
        "stop calling", "not now", "can't afford", "too expensive", "we're fine"
    ]
    
    pos_count = sum(1 for kw in positive_keywords if kw in text)
    neg_count = sum(1 for kw in negative_keywords if kw in text)
    
    if pos_count > neg_count:
        return "Positive"
    elif neg_count > pos_count:
        return "Negative"
    else:
        return "Neutral"
