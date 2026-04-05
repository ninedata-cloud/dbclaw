#!/usr/bin/env python3
"""Test that AI prompts contain restrictions against auto-starting services"""

def test_prompt_restrictions():
    from backend.agent.prompts import (
        DIAGNOSTIC_PROMPT,
        ADMINISTRATIVE_PROMPT,
        CONNECTION_FAILURE_DIAGNOSIS_PROMPT
    )
    
    # Keywords that should be present in restrictions
    restriction_keywords = [
        "禁止",
        "启动",
        "重启",
        "修改",
        "人工",
    ]
    
    prompts = {
        "DIAGNOSTIC_PROMPT": DIAGNOSTIC_PROMPT,
        "ADMINISTRATIVE_PROMPT": ADMINISTRATIVE_PROMPT,
        "CONNECTION_FAILURE_DIAGNOSIS_PROMPT": CONNECTION_FAILURE_DIAGNOSIS_PROMPT
    }
    
    print("Testing AI prompt restrictions...\n")
    
    all_passed = True
    for name, prompt in prompts.items():
        print(f"Testing {name}:")
        
        # Check for restriction section
        has_restriction_section = "🚨" in prompt and "操作限制" in prompt or "严格禁止" in prompt
        
        if has_restriction_section:
            print(f"  ✓ Has restriction section")
        else:
            print(f"  ✗ Missing restriction section")
            all_passed = False
        
        # Check for key restriction keywords
        missing_keywords = []
        for keyword in restriction_keywords:
            if keyword not in prompt:
                missing_keywords.append(keyword)
        
        if not missing_keywords:
            print(f"  ✓ Contains all restriction keywords")
        else:
            print(f"  ✗ Missing keywords: {', '.join(missing_keywords)}")
            all_passed = False
        
        # Check for specific forbidden operations
        forbidden_ops = ["systemctl start", "service start", "docker start"]
        found_forbidden = [op for op in forbidden_ops if op in prompt]
        
        if found_forbidden:
            print(f"  ✓ Explicitly mentions forbidden operations: {', '.join(found_forbidden)}")
        else:
            print(f"  ⚠ Does not explicitly list forbidden operations")
        
        print()
    
    if all_passed:
        print("✅ All prompts have proper restrictions!")
        return 0
    else:
        print("❌ Some prompts are missing restrictions!")
        return 1

if __name__ == "__main__":
    import sys
    sys.exit(test_prompt_restrictions())
