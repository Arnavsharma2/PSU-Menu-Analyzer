#!/usr/bin/env python3
"""
Final Refactored Menu Analyzer for Penn State with robust,
individual meal fetching and reliable analysis.
"""

import requests
from bs4 import BeautifulSoup
import json
import re
from typing import List, Dict, Tuple, Optional
from datetime import datetime
import os
import time

class MenuAnalyzer:
    def __init__(self, gemini_api_key: str = None, exclude_beef=False, exclude_pork=False,
                 vegetarian=False, debug=False):
        self.base_url = "https://www.absecom.psu.edu/menus/user-pages/daily-menu.cfm"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.debug = debug
        self.exclude_beef = exclude_beef
        self.exclude_pork = exclude_pork
        self.vegetarian = vegetarian

        gemini_api_key = 'AIzaSyC3k6AqP0dgg_LvOdKsNAorKWe9Xqf_bl0'
        
        self.gemini_api_key = gemini_api_key or os.getenv('GEMINI_API_KEY')
        if self.gemini_api_key:
            self.gemini_url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
                f"?key={self.gemini_api_key}"
            )
        elif self.debug:
            print("No Gemini API key provided. Using local analysis only.")

    def get_initial_form_data(self) -> Optional[Dict[str, Dict[str, str]]]:
        try:
            response = self.session.get(self.base_url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            options = {'campus': {}, 'meal': {}, 'date': {}}
            for name in options.keys():
                select_tag = soup.find('select', {'name': f'sel{name.capitalize()}' if name != 'date' else 'selMenuDate'})
                if select_tag:
                    for option in select_tag.find_all('option'):
                        value = option.get('value', '').strip()
                        text = option.get_text(strip=True)
                        if value and text:
                            options[name][text.lower()] = value # Use lowercase keys for easier matching
            return options
        except requests.RequestException as e:
            if self.debug:
                print(f"Error fetching initial page: {e}")
            return None

    def looks_like_food_item(self, text: str) -> bool:
        if not text or len(text.strip()) < 3 or len(text.strip()) > 70:
            return False
        
        text_lower = text.lower()
        non_food_keywords = [
            'select', 'menu', 'date', 'campus', 'print', 'view', 'nutrition', 'allergen',
            'feedback', 'contact', 'hours', 'location', 'penn state', 'altoona', 
            'port sky', 'cafe', 'kitchen', 'station', 'grill', 'deli', 'market',
            'made to order', 'action'
        ]
        if any(keyword in text_lower for keyword in non_food_keywords):
            return False
        
        if not any(c.isalpha() for c in text):
            return False

        return True

    def extract_items_from_meal_page(self, soup: BeautifulSoup) -> List[str]:
        """Extracts all food items from a page dedicated to a single meal."""
        items = set()
        # Search a wide variety of tags where food items might be listed
        for element in soup.find_all(['td', 'li', 'a', 'b', 'strong', 'span']):
            text = element.get_text(strip=True)
            if self.looks_like_food_item(text):
                items.add(text)
        return sorted(list(items))

    # NEW: This is the robust main workflow
    def run_analysis(self) -> Dict[str, List[Tuple[str, int, str]]]:
        if self.debug:
            print("Fetching initial form options...")
        
        form_options = self.get_initial_form_data()
        if not form_options:
            print("Could not fetch form data. Using fallback.")
            return self.get_fallback_data()

        # Find Altoona campus value
        campus_options = form_options.get('campus', {})
        altoona_value = next((val for name, val in campus_options.items() if 'altoona' in name), None)
        if not altoona_value:
            print("Could not find Altoona campus value. Using fallback.")
            return self.get_fallback_data()

        # Find today's date value
        date_options = form_options.get('date', {})
        today_str_key = datetime.now().strftime('%A, %B %d').lower()
        date_value = date_options.get(today_str_key)
        if not date_value:
            if date_options:
                first_available_date = list(date_options.keys())[0]
                date_value = list(date_options.values())[0]
                print(f"Warning: Today's menu ('{today_str_key}') not found. Using first available date: {first_available_date}")
            else:
                print("No dates found. Using fallback.")
                return self.get_fallback_data()

        # --- Main Scraping Loop ---
        daily_menu = {}
        meal_options = form_options.get('meal', {})
        
        for meal_name in ["Breakfast", "Lunch", "Dinner"]:
            meal_key = meal_name.lower()
            meal_value = meal_options.get(meal_key)
            
            if not meal_value:
                if self.debug:
                    print(f"Could not find form value for '{meal_name}'. Skipping.")
                continue

            try:
                form_data = {'selCampus': altoona_value, 'selMeal': meal_value, 'selMenuDate': date_value}
                if self.debug:
                    print(f"Fetching menu for {meal_name} with data: {form_data}")
                
                response = self.session.post(self.base_url, data=form_data, timeout=30)
                response.raise_for_status()
                meal_soup = BeautifulSoup(response.content, 'html.parser')
                
                items = self.extract_items_from_meal_page(meal_soup)
                if items:
                    daily_menu[meal_name] = items
                    if self.debug:
                        print(f"Found {len(items)} items for {meal_name}.")
                
                time.sleep(0.5) # Be polite to the server

            except requests.RequestException as e:
                if self.debug:
                    print(f"Error fetching {meal_name} menu: {e}")

        if not daily_menu:
            print("Failed to scrape any menu items from the website. Using fallback data.")
            return self.get_fallback_data()

        # --- Analysis and Filtering ---
        analyzed_results = self.analyze_menu_with_gemini(daily_menu) if self.gemini_api_key else self.analyze_menu_local(daily_menu)
        
        final_results = {}
        for meal, items in analyzed_results.items():
            final_results[meal] = self.apply_hard_filters(items)
        
        return final_results
    
    # ... (The rest of the analysis, filtering, and printing methods remain the same) ...

    def analyze_menu_with_gemini(self, daily_menu: Dict[str, List[str]]) -> Dict[str, List[Tuple[str, int, str]]]:
        exclusions = []
        if self.exclude_beef: exclusions.append("No beef.")
        if self.exclude_pork: exclusions.append("No pork.")
        if self.vegetarian: exclusions.append("Only vegetarian items.")
        restrictions_text = " ".join(exclusions) if exclusions else "None."

        prompt = f"""
        Analyze the following Penn State dining hall menu for health and protein content. My dietary restrictions are: {restrictions_text}

        For EACH meal period (Breakfast, Lunch, Dinner), identify the top 5 healthiest, highest-protein options that adhere to my restrictions.

        Return your response as a single, valid JSON object. The top-level keys must be "Breakfast", "Lunch", and "Dinner". The value for each key should be a list of objects, where each object contains three keys: "food_name" (string), "score" (an integer from 0 to 100), and "reasoning" (a brief string explanation).

        Menu:
        {json.dumps(daily_menu, indent=2)}
        """
        
        try:
            response = self.session.post(
                self.gemini_url,
                headers={"Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=60
            )
            response.raise_for_status()
            data = response.json()
            text_response = data["candidates"][0]["content"]["parts"][0]["text"]

            json_str = re.search(r'\{.*\}', text_response, re.DOTALL).group(0)
            parsed_json = json.loads(json_str)

            results = {}
            for meal, items in parsed_json.items():
                results[meal] = [(item.get('food_name'), item.get('score'), item.get('reasoning')) for item in items]
                results[meal].sort(key=lambda x: x[1], reverse=True)
            return results

        except Exception as e:
            if self.debug:
                print(f"Gemini analysis failed: {e}. Falling back to local analysis.")
            return self.analyze_menu_local(daily_menu)

    def apply_hard_filters(self, food_items: List[Tuple[str, int, str]]) -> List[Tuple[str, int, str]]:
        if not (self.exclude_beef or self.exclude_pork or self.vegetarian):
            return food_items

        filtered_list = []
        for food, score, reason in food_items:
            item_lower = food.lower()
            excluded = False
            if self.exclude_beef and "beef" in item_lower:
                excluded = True
            if self.exclude_pork and any(p in item_lower for p in ["pork", "bacon", "sausage", "ham"]):
                excluded = True
            if self.vegetarian and any(m in item_lower for m in ["beef", "pork", "chicken", "turkey", "fish", "salmon", "tuna", "bacon", "sausage", "ham"]):
                excluded = True
            
            if not excluded:
                filtered_list.append((food, score, reason))
        return filtered_list

    def get_fallback_data(self) -> Dict[str, List[Tuple[str, int, str]]]:
        fallback_menu = {
            "Breakfast": ["Scrambled Eggs", "Turkey Sausage", "Oatmeal", "Fresh Fruit"],
            "Lunch": ["Grilled Chicken Salad", "Turkey Club Sandwich", "Vegetable Soup", "Quinoa Bowl"],
            "Dinner": ["Baked Salmon", "Beef Stir-Fry", "Grilled Chicken Breast", "Pasta Primavera"]
        }
        analyzed = self.analyze_menu_local(fallback_menu)
        filtered_fallback = {}
        for meal, items in analyzed.items():
            filtered_fallback[meal] = self.apply_hard_filters(items)
        return filtered_fallback

    def analyze_menu_local(self, daily_menu: Dict[str, List[str]]) -> Dict[str, List[Tuple[str, int, str]]]:
        results = {}
        for meal, items in daily_menu.items():
            analyzed_items = self.analyze_food_health_local_list(items)
            analyzed_items.sort(key=lambda x: x[1], reverse=True)
            results[meal] = analyzed_items
        return results

    def analyze_food_health_local_list(self, food_items: List[str]) -> List[Tuple[str, int, str]]:
        health_scores = []
        protein_keywords = {'excellent': ['chicken', 'salmon', 'tuna', 'turkey'], 'good': ['beef', 'eggs', 'tofu', 'beans'], 'moderate': ['cheese', 'yogurt']}
        healthy_prep = {'excellent': ['grilled', 'baked', 'steamed'], 'good': ['sautéed'], 'poor': ['fried', 'creamy', 'battered']}
        for item in food_items:
            item_lower = item.lower()
            score = 50
            reasoning = []
            for level, keywords in protein_keywords.items():
                if any(kw in item_lower for kw in keywords):
                    score += {'excellent': 30, 'good': 20, 'moderate': 10}[level]
                    reasoning.append(f"High protein ({level})")
                    break
            for level, keywords in healthy_prep.items():
                if any(kw in item_lower for kw in keywords):
                    score += {'excellent': 20, 'good': 10, 'poor': -25}[level]
                    reasoning.append(f"Prep style ({level})")
                    break
            score = max(0, min(100, score))
            health_scores.append((item, score, ", ".join(reasoning) or "Standard option"))
        return health_scores

    def print_detailed_recommendations(self, results: Dict[str, List[Tuple[str, int, str]]], top_n: int = 5):
        print("\n" + "="*90)
        print("      PENN STATE ALTOONA - HEALTHY & HIGH-PROTEIN DINING RECOMMENDATIONS")
        print(f"      Generated on: {datetime.now().strftime('%A, %B %d, %Y')}")
        print("="*90)

        if not any(results.values()):
            print("\nSorry, no menu items could be found or recommended for today based on your preferences.")
            return

        for meal_name in ["Breakfast", "Lunch", "Dinner"]:
            items = results.get(meal_name)
            if items:
                print(f"\n--- {meal_name.upper()} ---")
                for i, (food, score, reason) in enumerate(items[:top_n], 1):
                    print(f"  {i}. {food:<40} | Score: {score}/100")
                    print(f"     └─ Analysis: {reason}")
            else:
                print(f"\n--- {meal_name.upper()} ---")
                print("  No items found or recommended for this meal.")
        print("\n" + "="*90)

if __name__ == "__main__":
    analyzer = MenuAnalyzer(
        gemini_api_key=os.getenv('GEMINI_API_KEY'),
        exclude_beef=False,
        exclude_pork=False,
        vegetarian=False,
        debug=True
    )
    
    final_recommendations = analyzer.run_analysis()
    analyzer.print_detailed_recommendations(final_recommendations)