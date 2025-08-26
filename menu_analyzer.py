import requests
from bs4 import BeautifulSoup
import json
import re
from typing import List, Dict, Tuple
from datetime import datetime
import os

class MenuAnalyzerWithGemini:
    def __init__(self, gemini_api_key: str = None):
        """
        Initialize with Google Gemini API
        Get your free API key from: https://aistudio.google.com/
        """
        self.base_url = "https://www.absecom.psu.edu/menus/user-pages/daily-menu.cfm"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        gemini_api_key='api key'
        
        # Set up Gemini API
        self.gemini_api_key = gemini_api_key or os.getenv('GEMINI_API_KEY')
        if self.gemini_api_key:
            self.gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_api_key}"
        else:
            print("Warning: No Gemini API key provided. Will use local analysis only.")
            print("Get your free key at: https://aistudio.google.com/")
    
    def analyze_food_with_gemini(self, food_items: List[str]) -> List[Tuple[str, int, str]]:
        """
        Use Google Gemini to analyze food healthiness and protein content
        """
        if not self.gemini_api_key:
            print("No Gemini API key available. Using local analysis.")
            return self.analyze_food_health_local(food_items)
        
        try:
            # Split into smaller batches to stay within API limits
            batch_size = 10
            all_results = []
            
            for i in range(0, len(food_items), batch_size):
                batch = food_items[i:i+batch_size]
                batch_results = self._analyze_batch_with_gemini(batch)
                all_results.extend(batch_results)
            
            return all_results
            
        except Exception as e:
            print(f"Gemini analysis failed: {e}")
            print("Falling back to local analysis.")
            return self.analyze_food_health_local(food_items)
    
    def _analyze_batch_with_gemini(self, food_batch: List[str]) -> List[Tuple[str, int, str]]:
        """Analyze a batch of foods with Gemini"""
        food_list = "\n".join([f"- {item}" for item in food_batch])
        
        prompt = f"""
        Analyze these dining hall food items for healthiness and protein content. 
        
        For each item, provide:
        1. Health score (0-100): Higher scores for nutritious, high-protein foods
        2. Brief reasoning focusing on protein content, preparation method, and nutritional value
        
        Scoring guidelines:
        - 80-100: Excellent (lean proteins, healthy prep, vegetables)
        - 60-79: Good (moderate protein, decent nutrition)
        - 40-59: Fair (some nutritional value)
        - 20-39: Poor (heavily processed, fried)
        - 0-19: Very poor (junk food, high sugar/fat)
        
        Food items:
        {food_list}
        
        Respond in this exact JSON format:
        {{
            "food_name_1": {{"score": 85, "reasoning": "Grilled chicken provides lean protein, salad adds vegetables"}},
            "food_name_2": {{"score": 45, "reasoning": "Fried preparation reduces nutritional value"}}
        }}
        """
        
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        
        response = requests.post(
            self.gemini_url,
            headers={'Content-Type': 'application/json'},
            json=payload,
            timeout=30
        )
        
        if response.status_code != 200:
            raise Exception(f"API Error: {response.status_code} - {response.text}")
        
        result = response.json()
        text_response = result['candidates'][0]['content']['parts'][0]['text']
        
        # Clean JSON formatting
        text_response = text_response.strip()
        if text_response.startswith("```json"):
            text_response = text_response[7:]
        if text_response.endswith("```"):
            text_response = text_response[:-3]
        
        # Parse JSON safely
        analysis_data = json.loads(text_response.strip())
        
        results = []
        for food_name, data in analysis_data.items():
            score = data.get("score")
            try:
                score = int(score) if score is not None else 50
            except (ValueError, TypeError):
                score = 50
            reasoning = data.get("reasoning", "No reasoning provided")
            results.append((food_name, score, reasoning))
        
        return results

    
    def analyze_food_health_local(self, food_items: List[str]) -> List[Tuple[str, int, str]]:
        """Enhanced local analysis as fallback"""
        health_scores = []
        
        # Enhanced keyword analysis
        protein_keywords = {
            'excellent': ['grilled chicken', 'baked fish', 'turkey breast', 'salmon', 'tuna'],
            'good': ['chicken', 'fish', 'turkey', 'beef', 'eggs', 'tofu', 'beans'],
            'moderate': ['cheese', 'nuts', 'yogurt', 'milk']
        }
        
        healthy_prep = {
            'excellent': ['grilled', 'baked', 'steamed', 'roasted', 'fresh'],
            'good': ['sautéed', 'stir-fry', 'broiled'],
            'poor': ['fried', 'deep-fried', 'battered', 'creamy']
        }
        
        healthy_ingredients = ['salad', 'vegetables', 'broccoli', 'spinach', 'whole grain', 'brown rice']
        unhealthy_ingredients = ['fries', 'pizza', 'burger', 'dessert', 'cake', 'candy']
        
        for item in food_items:
            item_lower = item.lower()
            score = 50
            reasoning_parts = []
            
            # Protein analysis
            for level, keywords in protein_keywords.items():
                matches = [kw for kw in keywords if kw in item_lower]
                if matches:
                    if level == 'excellent':
                        score += 25
                        reasoning_parts.append(f"Excellent protein source ({matches[0]})")
                    elif level == 'good':
                        score += 15
                        reasoning_parts.append(f"Good protein content ({matches[0]})")
                    else:
                        score += 8
                        reasoning_parts.append(f"Moderate protein ({matches[0]})")
                    break
            
            # Preparation method
            for level, keywords in healthy_prep.items():
                matches = [kw for kw in keywords if kw in item_lower]
                if matches:
                    if level == 'excellent':
                        score += 15
                        reasoning_parts.append(f"Healthy preparation ({matches[0]})")
                    elif level == 'good':
                        score += 8
                    elif level == 'poor':
                        score -= 20
                        reasoning_parts.append(f"⚠️ Unhealthy preparation ({matches[0]})")
                    break
            
            # Healthy ingredients
            healthy_matches = [ing for ing in healthy_ingredients if ing in item_lower]
            if healthy_matches:
                score += 10
                reasoning_parts.append(f"Contains healthy ingredients ({', '.join(healthy_matches[:2])})")
            
            # Unhealthy ingredients penalty
            unhealthy_matches = [ing for ing in unhealthy_ingredients if ing in item_lower]
            if unhealthy_matches:
                score -= 15
                reasoning_parts.append(f"⚠️ Less healthy option ({unhealthy_matches[0]})")
            
            # Ensure score is within bounds
            score = max(0, min(100, score))
            
            reasoning = "; ".join(reasoning_parts) if reasoning_parts else "Standard dining option"
            health_scores.append((item, score, reasoning))
        
        return health_scores
    
    # Include your existing methods here...
    def fetch_menu_page(self) -> BeautifulSoup:
        """Fetch the main menu page"""
        try:
            response = self.session.get(self.base_url)
            response.raise_for_status()
            return BeautifulSoup(response.content, 'html.parser')
        except requests.RequestException as e:
            print(f"Error fetching menu page: {e}")
            return None
    
    def select_altoona_menu(self, soup: BeautifulSoup) -> str:
        """Find and select the Altoona campus menu"""
        altoona_links = soup.find_all('a', string=re.compile(r'Altoona', re.IGNORECASE))
        
        if altoona_links:
            altoona_url = altoona_links[0].get('href')
            if altoona_url:
                if not altoona_url.startswith('http'):
                    altoona_url = f"https://www.absecom.psu.edu{altoona_url}"
                return altoona_url
        
        location_selects = soup.find_all('select', {'name': re.compile(r'location|campus', re.IGNORECASE)})
        for select in location_selects:
            altoona_options = select.find_all('option', string=re.compile(r'Altoona', re.IGNORECASE))
            if altoona_options:
                print(f"Found Altoona option: {altoona_options[0].get_text()}")
                form = select.find_parent('form')
                if form:
                    form_action = form.get('action', '')
                    if not form_action.startswith('http'):
                        form_action = f"https://www.absecom.psu.edu{form_action}"
                    
                    altoona_value = altoona_options[0].get('value')
                    if altoona_value:
                        form_data = {select.get('name'): altoona_value}
                        try:
                            response = self.session.post(form_action, data=form_data)
                            return response.url
                        except:
                            pass
                return self.base_url
        
        print("Could not find Altoona-specific menu. Using default.")
        return self.base_url
    
    def extract_meal_sections(self, soup: BeautifulSoup) -> Dict[str, List[str]]:
        """Extract meals - using your existing logic"""
        meals = {'Breakfast': [], 'Lunch': [], 'Dinner': []}
        
        # Your existing extraction logic here...
        all_text = soup.get_text()
        lines = [line.strip() for line in all_text.split('\n') if line.strip()]
        
        potential_foods = []
        for line in lines:
            if len(line) > 100:
                continue
            if self.looks_like_food_item(line):
                potential_foods.append(line)
        
        potential_foods = list(set(potential_foods))
        
        # Distribute among meals
        for i, food in enumerate(potential_foods):
            meal_index = i % 3
            meal_name = list(meals.keys())[meal_index]
            meals[meal_name].append(food)
        
        return meals
    
    def looks_like_food_item(self, text: str) -> bool:
        """Determine if text looks like a food item"""
        text = text.strip().lower()
        
        if len(text) < 3 or len(text) > 150:
            return False
        
        skip_terms = ['click', 'select', 'menu', 'page', 'home', 'login', 'sign', 'search', 
                     'view', 'print', 'back', 'next', 'previous', 'submit', 'cancel']
        if any(term in text for term in skip_terms):
            return False
        
        if len(re.sub(r'[a-zA-Z\s]', '', text)) > len(text) * 0.5:
            return False
        
        food_indicators = ['chicken', 'beef', 'pork', 'fish', 'turkey', 'pizza', 'burger', 
                          'sandwich', 'salad', 'soup', 'pasta', 'rice', 'bread', 'cheese',
                          'vegetables', 'fruit', 'grilled', 'baked', 'fried', 'roasted']
        
        if any(indicator in text for indicator in food_indicators):
            return True
        
        if len(text.split()) <= 8 and not any(char in text for char in ['@', 'http', '.com']):
            return True
        
        return False
    
    def run_analysis(self) -> Dict[str, List[Tuple[str, int, str]]]:
        """Main analysis method"""
        print("Fetching menu page...")
        soup = self.fetch_menu_page()
        if not soup:
            return {}
        
        print("Selecting Altoona menu...")
        altoona_url = self.select_altoona_menu(soup)
        
        if altoona_url != self.base_url:
            print(f"Fetching Altoona-specific page: {altoona_url}")
            response = self.session.get(altoona_url)
            soup = BeautifulSoup(response.content, 'html.parser')
        
        print("Extracting meal sections...")
        meals = self.extract_meal_sections(soup)

        results = {}
        for meal_name, food_items in meals.items():
            if food_items:
                print(f"Analyzing {meal_name} items with Gemini AI...")
                analyzed_items = self.analyze_food_with_gemini(food_items)

                # ✅ safe sort (prevents NoneType crash)
                analyzed_items.sort(
                    key=lambda x: (x[1] if isinstance(x[1], int) else -1),
                    reverse=True
                )

                results[meal_name] = analyzed_items
        
        return results

        
    
    def print_detailed_recommendations(self, results: Dict[str, List[Tuple[str, int, str]]], top_n: int = 5):
        """Print detailed recommendations with AI reasoning"""
        print("\n" + "="*90)
        print("AI-POWERED HEALTHY HIGH-PROTEIN FOOD RECOMMENDATIONS")
        print("="*90)
        
        all_items = []
        
        for meal_name, items in results.items():
            if items:
                print(f"\n{meal_name.upper()}:")
                print("-" * 60)
                
                for i, (food_item, score, reasoning) in enumerate(items[:top_n], 1):
                    print(f"{i}. {food_item}")
                    print(f"   Score: {score}/100")
                    print(f"   Analysis: {reasoning}")
                    print()
                    all_items.append((food_item, score, meal_name, reasoning))
        
        # Overall top recommendations
        print(f"\nOVERALL TOP {top_n} RECOMMENDATIONS:")
        print("-" * 70)
        all_items.sort(key=lambda x: x[1], reverse=True)
        
        for i, (food_item, score, meal_name, reasoning) in enumerate(all_items[:top_n], 1):
            print(f"{i}. {food_item} ({meal_name}) - Score: {score}/100")
            print(f"   {reasoning}")
            print()


def main():
    """Main execution with Gemini API"""
    # Set your Gemini API key (get free key from https://aistudio.google.com/)
    gemini_key = os.getenv('GEMINI_API_KEY')  # or replace with your key
    
    if not gemini_key:
        print("To use AI analysis, get a free API key from https://aistudio.google.com/")
        print("Then set it as environment variable: export GEMINI_API_KEY='your-key'")
        print("Or pass it directly to MenuAnalyzerWithGemini(gemini_api_key='your-key')")
        print("\nContinuing with local analysis only...\n")
    
    analyzer = MenuAnalyzerWithGemini(gemini_api_key=gemini_key)
    
    try:
        results = analyzer.run_analysis()
        
        if results:
            analyzer.print_detailed_recommendations(results, top_n=5)
        else:
            print("No menu data could be extracted.")
            
    except KeyboardInterrupt:
        print("\nAnalysis interrupted by user.")
    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()