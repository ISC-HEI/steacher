# Project Development Context for AI Assistant

This document provides context for the AI assistant to understand the development workflow of this project.

## TypeScript Compilation

The TypeScript code in the `frontend/` directory is automatically recompiled whenever a `.ts` file is saved. This is handled by a background process running the `npm run watch` command.

**You do not need to ask to recompile the TypeScript files.** Just assume they are up-to-date after any edit. 