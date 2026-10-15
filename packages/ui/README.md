# UI ownership

The current shared accessible primitives live in apps/web/src/components.tsx.
Do not create a separately versioned component package until another app consumes
them. Radix Dialog supplies focus management; Tailwind and the local design tokens
provide styling. This directory marks the extraction boundary, not an empty npm package.
