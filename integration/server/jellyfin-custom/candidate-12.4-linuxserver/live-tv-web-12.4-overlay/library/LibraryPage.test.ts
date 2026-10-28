import { CollectionType } from '@jellyfin/sdk/lib/generated-client/models/collection-type';
import { describe, expect, it } from 'vitest';

import { shouldRenderLiveTvCategories } from './liveTvCategoryTab';

describe('Live TV category tab preservation', () => {
    it('replaces only the native Live TV first tab with categories', () => {
        expect(shouldRenderLiveTvCategories(CollectionType.Livetv, 0)).toBe(true);
    });

    it('keeps native Guide, Channels, recordings and other libraries intact', () => {
        expect(shouldRenderLiveTvCategories(CollectionType.Livetv, 1)).toBe(false);
        expect(shouldRenderLiveTvCategories(CollectionType.Livetv, 2)).toBe(false);
        expect(shouldRenderLiveTvCategories(CollectionType.Livetv, 3)).toBe(false);
        expect(shouldRenderLiveTvCategories(CollectionType.Movies, 0)).toBe(false);
    });
});
