"""Assembling the objects a command needs out of the book.

Three commands wanted the same four loads in the same order, and the third one
got them by importing a private function out of another command module. That
works exactly until somebody moves it. So the loads live here, once, and the
command modules import a public name.
"""

from __future__ import annotations

from dripleg.cli.context import Context
from dripleg.diagnosis.batch import SurveyDiagnosis, diagnose_survey
from dripleg.diagnosis.engine import DiagnosisEngine
from dripleg.loss.register import LossRegister, build_loss_register
from dripleg.model.register import TrapRegister
from dripleg.repair.priority import WorkList, rank_jobs
from dripleg.repair.recommend import recommend
from dripleg.store.basis_repo import BasisRepository, SiteBasis
from dripleg.store.catalogue_repo import CatalogueRepository
from dripleg.store.rules_repo import RulesRepository
from dripleg.store.station_repo import StationRepository
from dripleg.store.survey_repo import SurveyRepository
from dripleg.survey.survey import Survey

__all__ = [
    "basis_for",
    "diagnosis_for",
    "engine_for",
    "loss_register_for",
    "register_for",
    "survey_for",
    "work_list_for",
]


def register_for(context: Context) -> TrapRegister:
    return StationRepository(context.book).load_register(context.site())


def survey_for(context: Context, reference: str) -> Survey:
    return SurveyRepository(context.book).get(context.site(), reference)


def basis_for(context: Context) -> SiteBasis:
    return BasisRepository(context.book).get_or_default(context.site())


def engine_for(context: Context) -> DiagnosisEngine:
    """The engine this site runs, with whatever it has switched off taken out."""

    return DiagnosisEngine(RulesRepository(context.book).rule_set_for(context.site()))


def diagnosis_for(context: Context, reference: str) -> SurveyDiagnosis:
    register = register_for(context)
    return diagnose_survey(register, survey_for(context, reference), engine_for(context))


def loss_register_for(context: Context, reference: str) -> LossRegister:
    register = register_for(context)
    basis = basis_for(context)
    return build_loss_register(
        register,
        diagnose_survey(register, survey_for(context, reference), engine_for(context)),
        basis.energy,
        basis.costs,
        basis.factor,
    )


def work_list_for(context: Context, reference: str) -> WorkList:
    losses = loss_register_for(context, reference)
    basis = basis_for(context)
    catalogue = CatalogueRepository(context.book).load_catalogue()
    return WorkList(
        rank_jobs([(row, recommend(row, basis.repairs, catalogue)) for row in losses.rows])
    )
