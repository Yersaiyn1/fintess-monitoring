import { translateText } from './translations';

describe('translateText', () => {
  it('translates supported UI strings for Kazakh and Russian', () => {
    expect(translateText('Settings', 'kk')).toBe('Баптаулар');
    expect(translateText('Settings', 'ru')).toBe('Настройки');
  });

  it('uses the English source text for English and untranslated strings', () => {
    expect(translateText('Settings', 'en')).toBe('Settings');
    expect(translateText('Server-provided message', 'ru')).toBe('Server-provided message');
  });
});
