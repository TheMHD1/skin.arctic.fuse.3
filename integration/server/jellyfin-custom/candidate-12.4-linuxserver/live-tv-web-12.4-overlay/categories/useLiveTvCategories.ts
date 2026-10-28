import type { Api } from '@jellyfin/sdk';
import type { AxiosRequestConfig } from 'axios';
import { useQuery } from '@tanstack/react-query';

import { type JellyfinApiContext, useApi } from 'hooks/useApi';
import type { ItemDtoQueryResult } from 'types/base/models/item-dto-query-result';

import { normalizeLiveTvCategories } from './liveTvCategories';

const CATEGORIES_STALE_TIME = 5 * 60 * 1000;
const CHANNELS_STALE_TIME = 30 * 1000;

const getRequestConfig = (
    api: Api,
    options: AxiosRequestConfig
): AxiosRequestConfig => ({
    ...(api.configuration.baseOptions as AxiosRequestConfig | undefined),
    ...options
});

const fetchLiveTvCategories = async (
    { api, user }: JellyfinApiContext,
    signal: AbortSignal
) => {
    if (!api || !user?.Id) {
        throw new Error('A Jellyfin API session is required');
    }

    const response = await api.axiosInstance.get<unknown>(
        api.getUri('/LiveTvCategories'),
        getRequestConfig(api, {
            params: { userId: user.Id },
            signal
        })
    );

    return normalizeLiveTvCategories(response.data);
};

const fetchLiveTvCategoryChannels = async (
    { api, user }: JellyfinApiContext,
    categoryId: string,
    startIndex: number,
    limit: number,
    signal: AbortSignal
) => {
    if (!api || !user?.Id) {
        throw new Error('A Jellyfin API session is required');
    }

    const response = await api.axiosInstance.get<ItemDtoQueryResult>(
        api.getUri(`/LiveTvCategories/${encodeURIComponent(categoryId)}/Channels`),
        getRequestConfig(api, {
            params: {
                userId: user.Id,
                startIndex,
                limit,
                addCurrentProgram: true
            },
            signal
        })
    );

    if (
        !response.data
        || !Array.isArray(response.data.Items)
        || !Number.isInteger(response.data.TotalRecordCount)
        || (response.data.TotalRecordCount ?? -1) < 0
    ) {
        throw new TypeError('Live TV category channel response is invalid');
    }

    return response.data;
};

export const getLiveTvCategoriesQueryKey = (
    basePath: string | undefined,
    userId: string | null | undefined
) => [ 'LiveTvCategories', basePath, userId ] as const;

export const getLiveTvCategoryChannelsQueryKey = (
    basePath: string | undefined,
    userId: string | null | undefined,
    categoryId: string | null,
    startIndex: number,
    limit: number
) => [
    ...getLiveTvCategoriesQueryKey(basePath, userId),
    categoryId,
    'Channels',
    { startIndex, limit }
] as const;

export const useLiveTvCategories = () => {
    const currentApi = useApi();

    return useQuery({
        queryKey: getLiveTvCategoriesQueryKey(
            currentApi.api?.basePath,
            currentApi.user?.Id
        ),
        queryFn: ({ signal }) => fetchLiveTvCategories(currentApi, signal),
        enabled: !!currentApi.api && !!currentApi.user?.Id,
        staleTime: CATEGORIES_STALE_TIME
    });
};

export const useLiveTvCategoryChannels = (
    categoryId: string | null,
    startIndex: number,
    limit: number
) => {
    const currentApi = useApi();

    return useQuery({
        queryKey: getLiveTvCategoryChannelsQueryKey(
            currentApi.api?.basePath,
            currentApi.user?.Id,
            categoryId,
            startIndex,
            limit
        ),
        queryFn: ({ signal }) => fetchLiveTvCategoryChannels(
            currentApi,
            categoryId!,
            startIndex,
            limit,
            signal
        ),
        enabled: !!currentApi.api && !!currentApi.user?.Id && !!categoryId,
        staleTime: CHANNELS_STALE_TIME
    });
};
