/**
 * Global Application Theme Configuration
 * 
 * Single source of truth for both Dark and Light mode color palettes.
 * Modify the values in `themes.dark` or `themes.light` to update the theme across the entire application.
 */

export type ThemeMode = 'dark' | 'light'

export interface ThemePalette {
  background: string
  surface: string
  card: string
  primary: string
  primaryHover: string
  success: string
  warning: string
  text: string
  secondaryText: string
  border: string
  input: string
  ring: string
}

export const themes: Record<ThemeMode, ThemePalette> = {
  dark: {
    background: '#070C18',     // Ultra Deep Midnight Obsidian
    surface: '#0F172A',        // Deep Slate Surface
    card: '#1B2436',           // Deep Card Slate
    primary: '#3B82F6',        // Vibrant Blue
    primaryHover: '#2563EB',   // Darker Blue hover
    success: '#22C55E',        // Emerald Green
    warning: '#F59E0B',        // Amber Gold
    text: '#F8FAFC',           // High Contrast White Text
    secondaryText: '#94A3B8',  // Secondary Muted Slate
    border: '#243047',         // Subtle Dark Border
    input: '#0F172A',          // Dark Input
    ring: '#3B82F6',           // Focus Ring
  },
  light: {
    background: '#F3F5ED',     // Eye-Relaxing Warm Linen / Soft Sage Cream
    surface: '#FAFBF7',        // Soft Warm Off-White Surface
    card: '#E6E9DF',           // Soothing Warm Neutral Card
    primary: '#245C75',        // Calming Deep Ocean Slate
    primaryHover: '#1B475B',   // Deep Blue-Teal
    success: '#2E7D47',        // Muted Forest Green
    warning: '#C27803',        // Warm Amber
    text: '#1C252C',           // Soft Dark Charcoal Text (No Harsh Black)
    secondaryText: '#556573',  // Relaxed Slate Text
    border: '#D8DDD0',         // Soft Warm Border
    input: '#E6E9DF',          // Soft Warm Input
    ring: '#245C75',           // Focus Ring
  },
}

/**
 * Converts a Hex color (#RRGGBB or #RGB) into space-separated HSL values ("H S% L%").
 */
export function hexToHslValues(hex: string): string {
  let c = hex.replace('#', '').trim()
  if (c.length === 3) {
    c = c.split('').map((x) => x + x).join('')
  }
  const num = parseInt(c, 16)
  if (isNaN(num)) return '0 0% 100%'

  const r = ((num >> 16) & 255) / 255
  const g = ((num >> 8) & 255) / 255
  const b = (num & 255) / 255

  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  let h = 0
  let s = 0
  const l = (max + min) / 2

  if (max !== min) {
    const d = max - min
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min)
    switch (max) {
      case r:
        h = (g - b) / d + (g < b ? 6 : 0)
        break
      case g:
        h = (b - r) / d + 2
        break
      case b:
        h = (r - g) / d + 4
        break
    }
    h /= 6
  }

  return `${Math.round(h * 360)} ${Math.round(s * 100)}% ${Math.round(l * 100)}%`
}

/**
 * Dynamically applies the specified theme mode ('dark' | 'light') to the document root element.
 */
export function applyTheme(mode: ThemeMode = 'dark') {
  if (typeof document === 'undefined') return

  const palette = themes[mode] || themes.dark
  const root = document.documentElement

  // Update root class list
  if (mode === 'light') {
    root.classList.add('light')
    root.classList.remove('dark')
  } else {
    root.classList.add('dark')
    root.classList.remove('light')
  }

  const cssVariables: Record<string, string> = {
    '--background': hexToHslValues(palette.background),
    '--foreground': hexToHslValues(palette.text),
    '--surface': hexToHslValues(palette.surface),
    '--card': hexToHslValues(palette.card),
    '--card-foreground': hexToHslValues(palette.text),
    '--popover': hexToHslValues(palette.surface),
    '--popover-foreground': hexToHslValues(palette.text),
    '--primary': hexToHslValues(palette.primary),
    '--primary-foreground': '0 0% 100%',
    '--secondary': hexToHslValues(palette.card),
    '--secondary-foreground': hexToHslValues(palette.text),
    '--muted': hexToHslValues(palette.card),
    '--muted-foreground': hexToHslValues(palette.secondaryText),
    '--accent': hexToHslValues(palette.card),
    '--accent-foreground': hexToHslValues(palette.text),
    '--success': hexToHslValues(palette.success),
    '--warning': hexToHslValues(palette.warning),
    '--destructive': '0 84% 60%',
    '--destructive-foreground': '0 0% 100%',
    '--border': hexToHslValues(palette.border),
    '--input': hexToHslValues(palette.input),
    '--ring': hexToHslValues(palette.ring),
    // Raw Hex values
    '--hex-background': palette.background,
    '--hex-surface': palette.surface,
    '--hex-card': palette.card,
    '--hex-primary': palette.primary,
    '--hex-success': palette.success,
    '--hex-warning': palette.warning,
    '--hex-text': palette.text,
    '--hex-secondary-text': palette.secondaryText,
  }

  for (const [key, value] of Object.entries(cssVariables)) {
    root.style.setProperty(key, value)
  }
}
