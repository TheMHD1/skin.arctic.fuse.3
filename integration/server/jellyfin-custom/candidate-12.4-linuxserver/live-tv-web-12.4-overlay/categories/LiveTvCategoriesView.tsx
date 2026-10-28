import type { SvgIconComponent } from '@mui/icons-material';
import Apps from '@mui/icons-material/Apps';
import ArrowBack from '@mui/icons-material/ArrowBack';
import Article from '@mui/icons-material/Article';
import ChevronRight from '@mui/icons-material/ChevronRight';
import ChildCare from '@mui/icons-material/ChildCare';
import LiveTv from '@mui/icons-material/LiveTv';
import Movie from '@mui/icons-material/Movie';
import MusicNote from '@mui/icons-material/MusicNote';
import NavigateBefore from '@mui/icons-material/NavigateBefore';
import NavigateNext from '@mui/icons-material/NavigateNext';
import SportsSoccer from '@mui/icons-material/SportsSoccer';
import { CollectionType } from '@jellyfin/sdk/lib/generated-client/models/collection-type';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import ButtonBase from '@mui/material/ButtonBase';
import ButtonGroup from '@mui/material/ButtonGroup';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import React, { type FC, useCallback, useEffect, useMemo, useRef } from 'react';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';

import {
    getLiveTvCategoryChannelsQueryKey,
    useLiveTvCategories,
    useLiveTvCategoryChannels
} from './useLiveTvCategories';
import {
    getCategoryPageSize,
    type LiveTvCategorySummary,
    parseCategoryStartIndex
} from './liveTvCategories';
import autoFocuser from 'components/autoFocuser';
import Cards from 'components/cardbuilder/Card/Cards';
import { CardShape } from 'components/cardbuilder/utils/shape';
import NoItemsMessage from 'components/common/NoItemsMessage';
import focusManager from 'components/focusManager';
import Loading from 'components/loading/LoadingComponent';
import ItemsContainer from 'elements/emby-itemscontainer/ItemsContainer';
import { useApi } from 'hooks/useApi';
import { useUserSettings } from 'hooks/useUserSettings';
import globalize from 'lib/globalize';
import type { CardOptions } from 'types/cardOptions';

const ALL_CHANNELS_ID = 'all-channels';
const CATEGORY_ID_PARAM = 'categoryId';
const CATEGORY_START_INDEX_PARAM = 'categoryStartIndex';
const CATEGORY_HISTORY_STATE = 'liveTvCategoryEntry';
const CHANNEL_FOCUS_HISTORY_STATE = 'liveTvCategoryFocusedChannelId';

interface CategoryEntry extends Omit<LiveTvCategorySummary, 'channelCount'> {
    channelCount: number | null;
}

interface CategoryTileProps {
    category: CategoryEntry;
    onSelect: (categoryId: string) => void;
}

type NavigationState = Record<string, unknown>;

const getNavigationState = (state: unknown): NavigationState => (
    typeof state === 'object' && state !== null ? state as NavigationState : {}
);

const getCategoryIcon = (category: CategoryEntry): SvgIconComponent => {
    if (category.id === ALL_CHANNELS_ID) return Apps;

    const name = category.name.toUpperCase();
    if (/SPORT|F1|MOTOGP|FIFA|NFL|NHL|NBA|MLB|MLS|CRICKET|OLYMPIC/.test(name)) {
        return SportsSoccer;
    }
    if (/KIDS|CHILD|FAMILY|FAMIL|ENFANT|COCUK|FEMIJET/.test(name)) {
        return ChildCare;
    }
    if (/CINEMA|MOVIE|FILM|SINEMA/.test(name)) return Movie;
    if (/MUSIC|MUZIK|MUZIKE|RADIO|RADIOFONO/.test(name)) return MusicNote;
    if (/NEWS|INFORMATION|HABER|LAJME/.test(name)) return Article;

    return LiveTv;
};

const CategoryTile: FC<CategoryTileProps> = ({ category, onSelect }) => {
    const Icon = getCategoryIcon(category);
    const handleClick = useCallback(() => {
        onSelect(category.id);
    }, [ category.id, onSelect ]);
    const channelText = category.channelCount === null ?
        globalize.translate('AllChannels') :
        `${category.channelCount.toLocaleString()} ${globalize.translate('Channels')}`;

    return (
        <Paper
            elevation={3}
            sx={{
                flex: {
                    xs: '1 1 calc(100% - 16px)',
                    sm: '1 1 calc(50% - 16px)',
                    md: '1 1 calc(33.333% - 16px)',
                    lg: '1 1 calc(25% - 16px)'
                },
                margin: 1,
                maxWidth: {
                    xs: 'calc(100% - 16px)',
                    sm: 'calc(50% - 16px)',
                    md: 'calc(33.333% - 16px)',
                    lg: 'calc(25% - 16px)'
                },
                minWidth: 0,
                overflow: 'visible'
            }}
        >
            <ButtonBase
                type='button'
                aria-label={`${category.name}, ${channelText}`}
                onClick={handleClick}
                sx={{
                    alignItems: 'center',
                    background: category.id === ALL_CHANNELS_ID ?
                        'linear-gradient(135deg, rgba(0, 164, 220, 0.30), rgba(112, 68, 184, 0.23))' :
                        'linear-gradient(145deg, rgba(128, 128, 128, 0.17), rgba(128, 128, 128, 0.07))',
                    border: '1px solid',
                    borderColor: category.id === ALL_CHANNELS_ID ?
                        'rgba(0, 164, 220, 0.52)' :
                        'rgba(128, 128, 128, 0.28)',
                    borderRadius: 1,
                    color: 'inherit',
                    display: 'flex',
                    justifyContent: 'flex-start',
                    minHeight: { xs: '5.5rem', sm: '6.4rem' },
                    padding: 2,
                    textAlign: 'left',
                    transition: 'transform 160ms ease, box-shadow 160ms ease',
                    width: '100%',
                    '& > * + *': {
                        marginLeft: 1.5
                    },
                    '[dir="rtl"] & > * + *': {
                        marginLeft: 0,
                        marginRight: 1.5
                    },
                    '&:hover': {
                        boxShadow: 6,
                        transform: 'translateY(-0.15rem) scale(1.01)'
                    },
                    '&:focus, &:focus-visible': {
                        boxShadow: 6,
                        outline: '0.2rem solid',
                        outlineColor: 'primary.main',
                        outlineOffset: '0.12rem',
                        transform: 'translateY(-0.15rem) scale(1.01)'
                    },
                    '@media (prefers-reduced-motion: reduce)': {
                        transition: 'none',
                        '&:hover, &:focus, &:focus-visible': {
                            transform: 'none'
                        }
                    }
                }}
            >
                <Box
                    sx={{
                        alignItems: 'center',
                        alignSelf: 'stretch',
                        backgroundColor: 'primary.main',
                        borderRadius: 1,
                        color: 'primary.contrastText',
                        display: 'flex',
                        flex: '0 0 3.2rem',
                        justifyContent: 'center',
                        minHeight: '3.2rem'
                    }}
                >
                    <Icon aria-hidden sx={{ fontSize: '2rem' }} />
                </Box>

                <Box sx={{ flex: '1 1 auto', minWidth: 0 }}>
                    <Typography
                        component='span'
                        sx={{
                            display: '-webkit-box',
                            fontWeight: 700,
                            lineHeight: 1.25,
                            overflow: 'hidden',
                            WebkitBoxOrient: 'vertical',
                            WebkitLineClamp: 2
                        }}
                    >
                        {category.name}
                    </Typography>
                    <Typography
                        component='span'
                        variant='body2'
                        sx={{
                            display: 'block',
                            marginTop: 0.5,
                            opacity: 0.72,
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap'
                        }}
                    >
                        {channelText}
                    </Typography>
                </Box>

                <ChevronRight aria-hidden sx={{ flex: '0 0 auto', opacity: 0.6 }} />
            </ButtonBase>
        </Paper>
    );
};

const LiveTvCategoriesView: FC = () => {
    const { api, __legacyApiClient__, user } = useApi();
    const { libraryPageSize } = useUserSettings();
    const location = useLocation();
    const navigate = useNavigate();
    const [ searchParams, setSearchParams ] = useSearchParams();
    const contentRef = useRef<HTMLDivElement>(null);
    const navigationState = getNavigationState(location.state);
    const focusedChannelId = typeof navigationState[CHANNEL_FOCUS_HISTORY_STATE] === 'string' ?
        navigationState[CHANNEL_FOCUS_HISTORY_STATE] :
        undefined;

    const categoryId = searchParams.get(CATEGORY_ID_PARAM);
    const startIndex = parseCategoryStartIndex(
        searchParams.get(CATEGORY_START_INDEX_PARAM)
    );
    const pageSize = getCategoryPageSize(libraryPageSize);
    const categoriesQuery = useLiveTvCategories();
    const channelsQuery = useLiveTvCategoryChannels(
        categoryId,
        startIndex,
        pageSize
    );

    const categories = categoriesQuery.data ?? [];
    const selectedCategory = categories.find(category => category.id === categoryId);
    const categoryChannelsQueryKey = useMemo(
        () => getLiveTvCategoryChannelsQueryKey(
            api?.basePath,
            user?.Id,
            categoryId,
            startIndex,
            pageSize
        ),
        [ api?.basePath, categoryId, pageSize, startIndex, user?.Id ]
    );
    const cardOptions = useMemo<CardOptions>(() => ({
        cardLayout: true,
        centerText: false,
        context: CollectionType.Livetv,
        coverImage: true,
        queryKey: categoryChannelsQueryKey,
        serverId: __legacyApiClient__?.serverId(),
        shape: CardShape.Square,
        showCurrentProgram: true,
        showCurrentProgramTime: true,
        showDetailsMenu: true,
        showTitle: true
    }), [ __legacyApiClient__, categoryChannelsQueryKey ]);

    const selectCategory = useCallback((selectedCategoryId: string) => {
        const nextParams = new URLSearchParams(searchParams);
        const nextState: NavigationState = {
            ...getNavigationState(location.state),
            [CATEGORY_HISTORY_STATE]: true
        };
        delete nextState[CHANNEL_FOCUS_HISTORY_STATE];
        nextParams.set('tab', '0');
        nextParams.set(CATEGORY_ID_PARAM, selectedCategoryId);
        nextParams.set(CATEGORY_START_INDEX_PARAM, '0');
        setSearchParams(nextParams, { state: nextState });
    }, [ location.state, searchParams, setSearchParams ]);

    const showAllChannels = useCallback(() => {
        const nextParams = new URLSearchParams(searchParams);
        const nextState = { ...getNavigationState(location.state) };
        delete nextState[CATEGORY_HISTORY_STATE];
        delete nextState[CHANNEL_FOCUS_HISTORY_STATE];
        nextParams.set('tab', '2');
        nextParams.delete(CATEGORY_ID_PARAM);
        nextParams.delete(CATEGORY_START_INDEX_PARAM);
        setSearchParams(nextParams, { state: nextState });
    }, [ location.state, searchParams, setSearchParams ]);

    const returnToCategories = useCallback(() => {
        const currentState = getNavigationState(location.state);
        if (currentState[CATEGORY_HISTORY_STATE] === true) {
            navigate(-1);
            return;
        }

        const nextParams = new URLSearchParams(searchParams);
        const nextState = { ...currentState };
        delete nextState[CATEGORY_HISTORY_STATE];
        delete nextState[CHANNEL_FOCUS_HISTORY_STATE];
        nextParams.delete(CATEGORY_ID_PARAM);
        nextParams.delete(CATEGORY_START_INDEX_PARAM);
        setSearchParams(nextParams, { replace: true, state: nextState });
    }, [ location.state, navigate, searchParams, setSearchParams ]);

    const setPage = useCallback((nextStartIndex: number) => {
        const nextParams = new URLSearchParams(searchParams);
        const nextState = { ...getNavigationState(location.state) };
        delete nextState[CHANNEL_FOCUS_HISTORY_STATE];
        nextParams.set(
            CATEGORY_START_INDEX_PARAM,
            Math.max(0, nextStartIndex).toString()
        );
        setSearchParams(nextParams, {
            replace: true,
            state: nextState
        });
        window.scrollTo(0, 0);
    }, [ location.state, searchParams, setSearchParams ]);

    const showPreviousPage = useCallback(() => {
        setPage(startIndex - pageSize);
    }, [ pageSize, setPage, startIndex ]);

    const showNextPage = useCallback(() => {
        setPage(startIndex + pageSize);
    }, [ pageSize, setPage, startIndex ]);

    const focusedChannelIdRef = useRef(focusedChannelId);
    useEffect(() => {
        if (focusedChannelId) {
            focusedChannelIdRef.current = focusedChannelId;
        }
    }, [ focusedChannelId ]);

    const rememberChannelFocus = useCallback((event: React.FocusEvent<HTMLDivElement>) => {
        const card = (event.target as HTMLElement).closest<HTMLElement>('[data-id]');
        const channelId = card?.dataset.id;
        if (!channelId || channelId === focusedChannelIdRef.current) return;

        focusedChannelIdRef.current = channelId;
        const routerHistoryState = getNavigationState(window.history.state);
        const currentNavigationState = getNavigationState(
            routerHistoryState.usr ?? location.state
        );

        window.history.replaceState(
            {
                ...routerHistoryState,
                usr: {
                    ...currentNavigationState,
                    [CHANNEL_FOCUS_HISTORY_STATE]: channelId
                }
            },
            document.title
        );
    }, [ location.state ]);

    const focusChannelCard = useCallback((channelId: string) => {
        const card = Array.from(
            contentRef.current?.querySelectorAll<HTMLElement>('[data-id]') ?? []
        ).find(element => element.dataset.id === channelId);
        const focusTarget = card?.matches('button, a, input, select, textarea, .focusable') ?
            card :
            card?.querySelector<HTMLElement>(
                'button:not(:disabled):not([tabindex="-1"]), a:not([tabindex="-1"]), .focusable'
            );

        if (focusTarget) {
            focusManager.focus(focusTarget);
            return true;
        }

        return false;
    }, []);

    const isContentPending = categoryId ?
        channelsQuery.isPending :
        categoriesQuery.isPending;

    useEffect(() => {
        if (!isContentPending) {
            if (focusedChannelId && focusChannelCard(focusedChannelId)) {
                return;
            }

            autoFocuser.autoFocus(contentRef.current);
        }
    }, [
        categoryId,
        focusedChannelId,
        focusChannelCard,
        isContentPending,
        channelsQuery.data,
        categoriesQuery.data
    ]);

    if (!categoryId) {
        if (categoriesQuery.isPending) return <Loading />;

        const totalChannels = categories.reduce(
            (total, category) => total + category.channelCount,
            0
        );
        const allChannels: CategoryEntry = {
            id: ALL_CHANNELS_ID,
            name: globalize.translate('AllChannels'),
            channelCount: null
        };

        return (
            <Box ref={contentRef} className='padded-bottom-page' sx={{ paddingTop: 2 }}>
                <Box
                    className='padded-left padded-right'
                    sx={{
                        alignItems: { xs: 'flex-start', sm: 'center' },
                        background: 'linear-gradient(125deg, rgba(0, 164, 220, 0.24), rgba(112, 68, 184, 0.16))',
                        border: '1px solid rgba(128, 128, 128, 0.26)',
                        borderRadius: 2,
                        display: 'flex',
                        flexDirection: { xs: 'column', sm: 'row' },
                        justifyContent: 'space-between',
                        marginBottom: 2,
                        marginLeft: '3.3%',
                        marginRight: '3.3%',
                        minHeight: '6rem',
                        paddingBottom: 2,
                        paddingTop: 2
                    }}
                >
                    <Box>
                        <Typography component='h1' variant='h4'>
                            Browse {globalize.translate('LiveTV')}
                        </Typography>
                        <Typography sx={{ marginTop: 0.5, opacity: 0.72 }}>
                            Choose a category to see its channels.
                        </Typography>
                    </Box>
                    <Typography
                        role='status'
                        aria-live='polite'
                        sx={{
                            backgroundColor: 'rgba(0, 0, 0, 0.2)',
                            border: '1px solid rgba(255, 255, 255, 0.12)',
                            borderRadius: 10,
                            fontWeight: 600,
                            marginLeft: { xs: 0, sm: 2 },
                            marginTop: { xs: 2, sm: 0 },
                            padding: '0.65rem 1rem',
                            whiteSpace: 'nowrap',
                            '[dir="rtl"] &': {
                                marginLeft: 0,
                                marginRight: { xs: 0, sm: 2 }
                            }
                        }}
                    >
                        {categories.length.toLocaleString()} categories · {totalChannels.toLocaleString()} channels
                    </Typography>
                </Box>

                {categoriesQuery.isError && (
                    <Alert severity='warning' className='padded-left padded-right'>
                        Live TV categories could not be loaded. All Channels is still available.
                    </Alert>
                )}

                {!categoriesQuery.isError && categories.length === 0 && (
                    <Alert severity='info' className='padded-left padded-right'>
                        No Live TV categories are available.
                    </Alert>
                )}

                <Box
                    sx={{
                        display: 'flex',
                        flexWrap: 'wrap',
                        margin: '0 calc(3.3% - 8px)'
                    }}
                >
                    <CategoryTile category={allChannels} onSelect={showAllChannels} />
                    {categories.map(category => (
                        <CategoryTile
                            key={category.id}
                            category={category}
                            onSelect={selectCategory}
                        />
                    ))}
                </Box>
            </Box>
        );
    }

    const items = channelsQuery.data?.Items ?? [];
    const totalRecordCount = channelsQuery.data?.TotalRecordCount ?? 0;
    const pageEnd = Math.min(startIndex + items.length, totalRecordCount);

    return (
        <Box ref={contentRef} className='padded-bottom-page' sx={{ paddingTop: 1 }}>
            <Stack
                className='padded-left padded-right'
                direction='row'
                spacing={1}
                sx={{ alignItems: 'center', marginBottom: 1 }}
            >
                <Button
                    color='inherit'
                    startIcon={<ArrowBack />}
                    onClick={returnToCategories}
                >
                    {globalize.translate('ButtonBack')}
                </Button>
                <Typography component='h1' variant='h5'>
                    {selectedCategory?.name ?? globalize.translate('Channels')}
                </Typography>
            </Stack>

            {channelsQuery.isPending && <Loading />}

            {channelsQuery.isError && (
                <Alert severity='error' className='padded-left padded-right'>
                    This category could not be loaded. Return to the category list or try again.
                </Alert>
            )}

            {channelsQuery.isSuccess && items.length === 0 && (
                <NoItemsMessage />
            )}

            {channelsQuery.isSuccess && items.length > 0 && (
                <Box onFocusCapture={rememberChannelFocus}>
                    <ItemsContainer
                        className='vertical-wrap padded-left padded-right'
                        queryKey={categoryChannelsQueryKey}
                        reloadItems={channelsQuery.refetch}
                    >
                        <Cards items={items} cardOptions={cardOptions} />
                    </ItemsContainer>
                </Box>
            )}

            {channelsQuery.isSuccess && totalRecordCount > pageSize && (
                <Stack
                    direction='row'
                    spacing={2}
                    sx={{
                        alignItems: 'center',
                        justifyContent: 'center',
                        marginTop: 2
                    }}
                >
                    <Typography>
                        {globalize.translate(
                            'ListPaging',
                            totalRecordCount ? startIndex + 1 : 0,
                            pageEnd,
                            totalRecordCount
                        )}
                    </Typography>
                    <ButtonGroup color='inherit' variant='text'>
                        <Button
                            title={globalize.translate('Previous')}
                            disabled={startIndex === 0}
                            onClick={showPreviousPage}
                        >
                            <NavigateBefore />
                        </Button>
                        <Button
                            title={globalize.translate('Next')}
                            disabled={startIndex + pageSize >= totalRecordCount}
                            onClick={showNextPage}
                        >
                            <NavigateNext />
                        </Button>
                    </ButtonGroup>
                </Stack>
            )}
        </Box>
    );
};

export default LiveTvCategoriesView;
