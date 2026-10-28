import { CollectionType } from '@jellyfin/sdk/lib/generated-client/models/collection-type';

// Native Live TV owns every tab except its first Programs/recommended tab.
export const shouldRenderLiveTvCategories = (type: CollectionType, activeTab: number): boolean => (
    type === CollectionType.Livetv && activeTab === 0
);
