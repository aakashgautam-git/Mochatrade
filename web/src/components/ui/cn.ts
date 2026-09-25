/** Join class names, dropping falsy parts. A four-line clsx, not a dependency. */
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}
