---
name: implementFeatureStepByStep
description: Implement complex feature iteratively from specification with commits and debugging
argument-hint: Feature name or documentation section reference
---

You are implementing a complex feature following a structured plan. Your task is to:

## Implementation Process

1. **Read the Specification**
   - Locate and read the feature plan in the project documentation
   - Understand all steps and their dependencies
   - Identify backend, frontend, database, and configuration requirements

2. **Implement Step-by-Step**
   - Implement ONE step at a time from the plan
   - For each step:
     - Write backend API endpoints if needed (routes, schemas, business logic)
     - Create or update database models with proper relationships and indexes
     - Implement frontend UI components (HTML, JavaScript functions, event handlers)
     - Add CSS styling that matches existing design patterns
     - Validate syntax and check for errors
   - Make a detailed git commit after each step with:
     - Descriptive commit message following conventional commits format
     - List of what was added/changed
     - Explanation of functionality
     - Reference to the step number

3. **Update Documentation**
   - After completing all steps, update the specification document
   - Mark completed steps with ✅
   - Add implementation details (file paths, function names, endpoint URLs)
   - Include usage examples and common tasks
   - Document any remaining incomplete tasks

4. **Production Debugging** (when issues arise)
   - Analyze server logs to identify specific errors
   - Diagnose root cause (authentication, configuration, missing dependencies, etc.)
   - Compare working vs non-working code patterns
   - Search codebase for similar working implementations
   - Fix issues systematically:
     - Token/auth issues: check localStorage keys, header format
     - Config issues: verify environment variables, Field aliases, Settings class
     - API issues: validate endpoint registration, dependencies, response format
   - Test fixes locally before deploying
   - Commit fixes with clear problem/solution description

5. **Best Practices**
   - Use parallel tool invocations for independent read operations
   - Use multi_replace_string_in_file for multiple related edits
   - Follow existing code patterns and conventions
   - Ensure proper error handling and user feedback
   - Add loading states and success/error messages in UI
   - Keep commits atomic and well-documented

## Example Workflow

Given a specification document with steps 1-9:
- Read specification and understand overall architecture
- Implement Step 1 (e.g., backend API endpoints) → commit
- Implement Step 2 (e.g., data models) → commit  
- Implement Step 3 (e.g., reconciliation logic) → commit
- ...continue for all steps...
- Implement Step 9 (UI components) → commit
- Add CSS styling → commit
- Update documentation with completion status → commit
- If production errors occur: diagnose → fix → commit
- Push changes and verify deployment

## Key Considerations

- **Backend**: Ensure proper authentication, validation, error handling
- **Frontend**: Use existing helper functions (e.g., getAuthToken()), consistent UI patterns
- **Database**: Add indexes for performance, proper relationships, migrations if needed
- **Configuration**: Use Field aliases for environment variables in Pydantic v2
- **Testing**: Validate locally before deployment, check for breaking changes
- **Documentation**: Keep specification in sync with implementation status

Apply this methodology to implement the specified feature systematically and reliably.
