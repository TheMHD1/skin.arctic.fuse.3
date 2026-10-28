const DEFAULT_PAGE_SIZE = 100;
const MAX_PAGE_SIZE = 250;

export interface LiveTvCategorySummary {
    id: string;
    name: string;
    channelCount: number;
}

const isRecord = (value: unknown): value is Record<string, unknown> => (
    typeof value === 'object' && value !== null
);

export const normalizeLiveTvCategories = (
    payload: unknown
): LiveTvCategorySummary[] => {
    let source: unknown[] | undefined;
    if (Array.isArray(payload)) {
        source = payload;
    } else if (isRecord(payload) && Array.isArray(payload.Items)) {
        source = payload.Items;
    }

    if (!source) {
        throw new TypeError('Live TV category response is not an array');
    }

    const ids = new Set<string>();
    const categories: LiveTvCategorySummary[] = [];

    for (const value of source) {
        if (!isRecord(value)) continue;

        const { id, name, channelCount } = value;
        if (
            typeof id !== 'string'
            || id.length === 0
            || typeof name !== 'string'
            || name.length === 0
            || typeof channelCount !== 'number'
            || !Number.isInteger(channelCount)
            || channelCount < 0
            || ids.has(id)
        ) {
            continue;
        }

        ids.add(id);
        categories.push({ id, name, channelCount });
    }

    // Server order pins curated collections first and preserves provider order.
    return categories;
};

export const getCategoryPageSize = (configuredPageSize: number) => {
    if (!Number.isFinite(configuredPageSize) || configuredPageSize <= 0) {
        return DEFAULT_PAGE_SIZE;
    }

    return Math.min(Math.trunc(configuredPageSize), MAX_PAGE_SIZE);
};

export const parseCategoryStartIndex = (value: string | null) => {
    if (!value || !/^\d+$/.test(value)) return 0;

    const parsed = Number(value);
    return Number.isSafeInteger(parsed) ? parsed : 0;
};
