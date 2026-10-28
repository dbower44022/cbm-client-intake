<?php
/*
 * GET /api/v1/SortedList/{entityType} — a page of records sorted on several
 * columns (prds/shared-grid-plan.md § 8; Doug's ruling 10-28-26 to try a
 * change to the CRM itself).
 *
 * EspoCRM's own list endpoint sorts by one field. This takes the same query
 * parameters (where[…], select, maxSize, offset, textFilter) plus
 *
 *     orderList=leadStatus:asc,name:desc
 *
 * (not "sortBy": EspoCRM reads that as an old name for its own one-field
 * orderBy and refuses the list — found on crm-test 10-28-26).
 *
 * and applies the same access control as the standard list: the caller must
 * read the entity type, the query is built with strict access control (the
 * caller's own roles and teams), and attributes the caller may not read are
 * removed from every row. The total is NOT returned — callers take it from the
 * standard list endpoint with the same where.
 *
 * Installed by scripts/install_sorted_list.sh; removing these two files and
 * rebuilding takes it away again.
 */

namespace Espo\Custom\Api;

use Espo\Core\Acl;
use Espo\Core\Api\Action;
use Espo\Core\Api\Request;
use Espo\Core\Api\Response;
use Espo\Core\Api\ResponseComposer;
use Espo\Core\Exceptions\BadRequest;
use Espo\Core\Exceptions\Forbidden;
use Espo\Core\Record\SearchParamsFetcher;
use Espo\Core\Select\SelectBuilderFactory;
use Espo\ORM\EntityManager;

class SortedList implements Action
{
    private const MAX_KEYS = 6;
    private const MAX_SIZE = 200;

    public function __construct(
        private SearchParamsFetcher $searchParamsFetcher,
        private SelectBuilderFactory $selectBuilderFactory,
        private EntityManager $entityManager,
        private Acl $acl
    ) {}

    public function process(Request $request): Response
    {
        $entityType = (string) $request->getRouteParam('entityType');

        if (!$entityType || !$this->entityManager->hasRepository($entityType)) {
            throw new BadRequest("Unknown entity type.");
        }
        if (!$this->acl->check($entityType, Acl\Table::ACTION_READ)) {
            throw new Forbidden("No read access to {$entityType}.");
        }

        $defs = $this->entityManager->getDefs()->getEntity($entityType);
        $order = [];

        foreach (explode(',', (string) ($request->getQueryParam('orderList') ?? '')) as $piece) {
            $piece = trim($piece);
            if ($piece === '') {
                continue;
            }
            [$attribute, $direction] = array_pad(explode(':', $piece, 2), 2, 'asc');
            $attribute = trim($attribute);
            if (!$defs->hasAttribute($attribute)) {
                throw new BadRequest("Cannot sort by '{$attribute}'.");
            }
            $order[] = [$attribute, strtolower(trim($direction)) === 'desc' ? 'DESC' : 'ASC'];
            if (count($order) >= self::MAX_KEYS) {
                break;
            }
        }
        // A last key that always differs, so pages never overlap.
        $order[] = ['id', 'ASC'];

        $searchParams = $this->searchParamsFetcher->fetch($request);
        if (($searchParams->getMaxSize() ?? 0) > self::MAX_SIZE) {
            throw new BadRequest("maxSize may not exceed " . self::MAX_SIZE . ".");
        }

        $query = $this->selectBuilderFactory
            ->create()
            ->from($entityType)
            ->withStrictAccessControl()
            ->withSearchParams($searchParams)
            ->buildQueryBuilder()
            ->order($order)
            ->build();

        $forbidden = array_flip($this->acl->getScopeForbiddenAttributeList($entityType, Acl\Table::ACTION_READ));
        $list = [];

        foreach ($this->entityManager->getRDBRepository($entityType)->clone($query)->find() as $entity) {
            $row = get_object_vars($entity->getValueMap());
            $list[] = array_diff_key($row, $forbidden);
        }

        return ResponseComposer::json(['list' => $list]);
    }
}
