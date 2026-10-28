import { describe, expect, it } from 'vitest';

import {
    getCategoryPageSize,
    normalizeLiveTvCategories,
    parseCategoryStartIndex
} from './liveTvCategories';

describe('Live TV categories', () => {
    it('normalizes and deduplicates without overriding server priority', () => {
        const result = normalizeLiveTvCategories({
            Items: [
                { id: 'news-10', name: 'News 10', channelCount: 3 },
                { id: 'news-2', name: 'News 2', channelCount: 4 },
                { id: 'news-2', name: 'Duplicate', channelCount: 99 },
                { id: '', name: 'Invalid', channelCount: 1 },
                { id: 'negative', name: 'Invalid', channelCount: -1 }
            ]
        });

        expect(result).toEqual([
            { id: 'news-10', name: 'News 10', channelCount: 3 },
            { id: 'news-2', name: 'News 2', channelCount: 4 }
        ]);
    });

    it('rejects a malformed summary response', () => {
        expect(() => normalizeLiveTvCategories({ error: true })).toThrow(TypeError);
    });

    it('bounds API page sizes and falls back when pagination is disabled', () => {
        expect(getCategoryPageSize(0)).toBe(100);
        expect(getCategoryPageSize(50)).toBe(50);
        expect(getCategoryPageSize(500)).toBe(250);
    });

    it('accepts only safe non-negative URL start indexes', () => {
        expect(parseCategoryStartIndex('200')).toBe(200);
        expect(parseCategoryStartIndex('-1')).toBe(0);
        expect(parseCategoryStartIndex('2.5')).toBe(0);
        expect(parseCategoryStartIndex('not-a-number')).toBe(0);
        expect(parseCategoryStartIndex(null)).toBe(0);
    });
});
