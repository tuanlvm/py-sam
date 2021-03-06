from argparse import ArgumentParser
import os

from sam.condor.condorizable import Condorizable
from sam.corpus.corpus import CorpusReader
from sam.vem.model import VEMModel
import sam.log as log

SAVE_MODEL_INTERVAL = 10
SAVE_TOPICS_INTERVAL = 10


class VEMTask(Condorizable):
    binary = 'sam/vem/__main__.py'

    def check_args(self, argv):
        parser = ArgumentParser()
        parser.add_argument('--model', type=str, required=True, help='Save model to <path>, or resume running from that state')
        parser.add_argument('--corpus', type=str, help='Path to SAM corpus')

        parser.add_argument('-T', '--T', type=int, default=10, help='Number of topics')
        parser.add_argument('--iterations', type=int, default=500, help='Run VEM for <n> iterations')
        parser.add_argument('--write_topic_weights', type=str, help='Write topic weights to <path>')
        parser.add_argument('--write_topics', type=str, help='Write topics to <path>')
        options = parser.parse_args(argv[1:])

        # If the model doesn't already exist (we're creating a new one), we need to know where the corpus lives
        if not os.path.exists(options.model):
            if options.corpus is None:
                parser.error('Must provide --corpus when creating a new model')
            if not os.path.exists(options.corpus):
                parser.error('Corpus file %s does not exist!' % options.corpus)

        self.add_output_file(options.model)
        if options.write_topic_weights:
            self.add_output_file(options.write_topic_weights)
        if options.write_topics:
            self.add_output_file(options.write_topics)

        return options

    def run(self, options):
        if os.path.exists(options.model):
            log.info('Loading model snapshot from %s' % options.model)
            model = VEMModel.load(options.model)
        else:
            # Initialize a model from scratch
            log.info('Initializing new model on %s [T=%d]' % (options.corpus, options.T))
            reader = CorpusReader(options.corpus, data_series='sam')
            model = VEMModel(reader=reader, T=options.T)

        while model.iteration < options.iterations:
            log.info('** Iteration %d / %d **' % (model.iteration + 1, options.iterations))
            model.run_one_iteration()

            if model.iteration % SAVE_MODEL_INTERVAL == 0:
                log.info('Saving model snapshot...')
                model.save(options.model)

            if model.iteration % SAVE_TOPICS_INTERVAL == 0:
                if options.write_topics:
                    log.info('Saving topics to %s' % options.write_topics)
                    with open(options.write_topics, 'w') as f:
                        model.write_topics(f)

                if options.write_topic_weights:
                    log.info('Saving topic weights to %s' % options.write_topic_weights)
                    with open(options.write_topic_weights, 'w') as f:
                        model.write_topic_weights_arff(f)

        if options.write_topics:
            log.info('Saving topics to %s' % options.write_topics)
            with open(options.write_topics, 'w') as f:
                model.write_topics(f)

        if options.write_topic_weights:
            log.info('Saving topic weights to %s' % options.write_topic_weights)
            with open(options.write_topic_weights, 'w') as f:
                model.write_topic_weights_arff(f)
        model.save(options.model)


def run_sam_batch(vem_configs):
    """
    Runs SAM on every experimental configuration defined by 'config'.  Jobs that have already been run or are
    current running (i.e. for which the model file already exists, or for which a lock file exists) will be skipped.
    """
    for job_settings in vem_configs:
        model_file = job_settings['model']
        if os.path.exists(model_file):
            log.warning('Model %s already exists; skipping' % os.path.basename(model_file))
            continue
        if Condorizable.is_locked(model_file):
            log.warning('Model %s is locked; check that another job isn''t writing to this path' %\
                  os.path.basename(model_file))
            continue

        VEMTask(kw=job_settings)
