import { CollectionType } from '@jellyfin/sdk/lib/generated-client/models/collection-type';
import LibraryPage from 'apps/modern/features/libraries/components/LibraryPage';
import React, { type FC } from 'react';

const LiveTv: FC = () => {
    return (
        <LibraryPage type={CollectionType.Livetv} />
    );
};

export default LiveTv;
